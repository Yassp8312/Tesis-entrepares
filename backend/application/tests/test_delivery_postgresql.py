"""Ejecutor real contra PostgreSQL; solo transportes en memoria y datos sintéticos."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import StringIO
from queue import Queue
from threading import Barrier, Event
from time import monotonic
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, transaction

from application.delivery.sources import DeliveryTemplate
from application.delivery.transports import DjangoEmailTransport
from application.delivery.worker import OutboxWorker
from core.clock import FixedClock
from core.correlation import OperationContext
from modules.identity.models import Account, EmailChallenge
from modules.notifications.commands import delivery as delivery_commands
from modules.notifications.commands.delivery import claim_next, finish_claim, recover_expired
from modules.notifications.contracts.delivery import (
    DeliveryError,
    DeliveryResult,
    PreparedEmail,
    RenderedEmail,
    TransportResult,
    WorkerPolicy,
)
from modules.notifications.models import DeliveryAttempt, Notice, OutboxMessage
from modules.opportunities.models import LifecycleEvent, Opportunity
from modules.organizations.models import Organization, OrganizationVerification, Representation

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
DAY = timedelta(days=1)
POLICY = WorkerPolicy(lease_seconds=60, retry_seconds=5, max_retry_seconds=20)


class MemoryTransport:
    supports_idempotency = False
    timeout_seconds = 1

    def __init__(self, result=DeliveryResult.ACCEPTED):
        self.result, self.messages = result, []

    def send(self, message):
        assert not connection.in_atomic_block
        self.messages.append(message)
        return TransportResult(self.result)


def context(now=NOW):
    return OperationContext.start(clock=FixedClock(now))


def email_template(render=None):
    return DeliveryTemplate(
        "synthetic.confirmation",
        "challenge",
        render or (lambda ctx: RenderedEmail("Aviso sintético", "Mensaje sintético")),
        purpose="email_confirmation",
        key_versions=frozenset({"v1"}),
    )


def worker(transport=None, templates=None, policy=POLICY):
    return OutboxWorker(
        transport=transport or MemoryTransport(),
        templates=(email_template(),) if templates is None else templates,
        policy=policy,
    )


@pytest.fixture
def source():
    account = Account.objects.create_user("delivery-synthetic@example.invalid")
    challenge = EmailChallenge.objects.create(
        account=account,
        purpose="email_confirmation",
        email_snapshot=account.email,
        key_version="v1",
        created_at=NOW - DAY,
        expires_at=NOW + DAY,
    )
    message = OutboxMessage.objects.create(
        challenge=challenge,
        recipient_account=account,
        channel="email",
        destination=account.email,
        template_key="synthetic.confirmation",
        payload={"challenge_id": str(challenge.pk)},
        idempotency_key=f"synthetic:{uuid4()}",
        available_at=NOW,
    )
    return account, challenge, message


def claim(now=NOW, policy=POLICY, retry_unknown=False):
    with transaction.atomic():
        return claim_next(policy=policy, now=now, retry_unknown=retry_unknown)


def finish(token, result, now=NOW, policy=POLICY, **kwargs):
    with transaction.atomic():
        return finish_claim(
            claim=token, outcome=TransportResult(result), policy=policy, now=now, **kwargs
        )


def test_send_happens_after_claim_and_preparation_commits_and_records_acceptance(source):
    account, challenge, message = source

    class ObservingTransport(MemoryTransport):
        def send(self, prepared):
            def observer():
                try:
                    row = OutboxMessage.objects.get(pk=message.pk)
                    return row.status, DeliveryAttempt.objects.get(outbox=row).result
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(observer).result(timeout=5) == ("processing", "running")
            return super().send(prepared)

    transport = ObservingTransport()
    result = worker(transport).run_once(operation=context())
    message.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(outbox=message)
    assert result.status == "accepted" and message.status == "sent" and message.sent_at == NOW
    assert (
        message.lease_until is None and attempt.result == "accepted" and attempt.finished_at == NOW
    )
    assert attempt.attempt_no == 1 and attempt.error_code is None
    assert transport.messages[0].destination == account.email
    assert "Mensaje" not in str(attempt.__dict__)
    assert worker(transport).run_once(operation=context()).status == "empty"
    assert len(transport.messages) == 1


def test_worker_and_adapter_cannot_send_from_outer_transaction(source):
    transport = MemoryTransport()
    with transaction.atomic():
        with pytest.raises(RuntimeError):
            worker(transport).run_once(operation=context())
        with pytest.raises(RuntimeError):
            DjangoEmailTransport().send(
                PreparedEmail(
                    source[2].pk, "synthetic", source[0].email, RenderedEmail("Asunto", "Texto")
                )
            )
    assert not transport.messages and not DeliveryAttempt.objects.exists()


@pytest.mark.parametrize(
    "change",
    [
        "consumed",
        "invalidated",
        "expired",
        "email",
        "inactive",
        "foreign",
        "purpose",
        "version",
        "destination",
        "payload",
        "template",
        "sample",
    ],
)
def test_source_and_payload_are_revalidated_before_transport(source, change):
    account, challenge, message = source
    if change == "consumed":
        EmailChallenge.objects.filter(pk=challenge.pk).update(consumed_at=NOW)
    if change == "invalidated":
        EmailChallenge.objects.filter(pk=challenge.pk).update(invalidated_at=NOW)
    if change == "expired":
        EmailChallenge.objects.filter(pk=challenge.pk).update(expires_at=NOW)
    if change == "email":
        Account.objects.filter(pk=account.pk).update(email="changed@example.invalid")
    if change == "inactive":
        Account.objects.filter(pk=account.pk).update(is_active=False)
    if change == "foreign":
        OutboxMessage.objects.filter(pk=message.pk).update(
            recipient_account=Account.objects.create_user("foreign@example.invalid")
        )
    if change == "purpose":
        EmailChallenge.objects.filter(pk=challenge.pk).update(purpose="password_reset")
    if change == "version":
        EmailChallenge.objects.filter(pk=challenge.pk).update(key_version="unrecognized")
    if change == "destination":
        OutboxMessage.objects.filter(pk=message.pk).update(destination="other@example.invalid")
    if change == "payload":
        OutboxMessage.objects.filter(pk=message.pk).update(payload={"token": "synthetic-secret"})
    if change == "template":
        OutboxMessage.objects.filter(pk=message.pk).update(template_key="unknown")
    if change == "sample":
        EmailChallenge.objects.filter(pk=challenge.pk).update(key_version="sample-only")
    transport = MemoryTransport()
    outcome = worker(transport).run_once(operation=context())
    message.refresh_from_db()
    assert not transport.messages and message.status in ("cancelled", "failed")
    attempt = DeliveryAttempt.objects.get(outbox=message)
    assert attempt.result == "failed" and attempt.error_code in {
        item.value for item in DeliveryError
    }
    assert "synthetic-secret" not in (attempt.error_code or "")
    assert worker(transport).run_once(operation=context(NOW + DAY)).status == "empty"
    assert outcome.status in ("cancelled", "failed")


def test_temporary_retries_obey_backoff_and_limit(source):
    transport = MemoryTransport(DeliveryResult.TEMPORARY)
    runtime = worker(transport)
    assert runtime.run_once(operation=context()).status == "temporary"
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=4))).status == "empty"
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=5))).status == "temporary"
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=14))).status == "empty"
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=15))).status == "temporary"
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=50))).status == "empty"
    assert list(
        DeliveryAttempt.objects.order_by("attempt_no").values_list("attempt_no", flat=True)
    ) == [1, 2, 3]
    assert len(transport.messages) == 3


@pytest.mark.parametrize("mode", ["permanent", "unknown", "exception"])
def test_permanent_and_uncertain_outcomes_are_not_automatically_retried(source, mode):
    class Transport(MemoryTransport):
        def send(self, message):
            if mode == "exception":
                raise RuntimeError("private-destination-and-token")
            return TransportResult(DeliveryResult(mode))

    runtime = worker(Transport())
    assert runtime.run_once(operation=context()).status in ("permanent", "unknown")
    assert runtime.run_once(operation=context(NOW + timedelta(seconds=30))).status == "empty"
    attempt = DeliveryAttempt.objects.get()
    assert attempt.result == ("failed" if mode == "permanent" else "unknown")
    assert "private" not in attempt.error_code and attempt.provider_reference is None


@pytest.mark.parametrize("idempotent", [False, True])
def test_uncertain_retry_needs_both_policy_and_transport_idempotency(source, idempotent):
    transport = MemoryTransport(DeliveryResult.UNKNOWN)
    transport.supports_idempotency = idempotent
    policy = WorkerPolicy(lease_seconds=60, retry_seconds=5, retry_unknown=True)
    runtime = worker(transport, policy=policy)
    runtime.run_once(operation=context())
    outcome = runtime.run_once(operation=context(NOW + timedelta(seconds=6)))
    assert outcome.status == ("unknown" if idempotent else "empty")


def test_expired_claim_is_recorded_unknown_and_stale_worker_cannot_finalize(source):
    token = claim()
    assert token is not None
    with transaction.atomic():
        assert (
            recover_expired(policy=POLICY, now=token.lease_until - timedelta(microseconds=1)) == 0
        )
        assert recover_expired(policy=POLICY, now=token.lease_until) == 1
    assert DeliveryAttempt.objects.get().result == "unknown"
    assert not finish(token, DeliveryResult.ACCEPTED, now=token.lease_until)
    assert claim(now=token.lease_until + DAY) is None
    policy = WorkerPolicy(lease_seconds=60, retry_seconds=5, retry_unknown=True)
    successor = claim(
        now=token.lease_until + timedelta(seconds=6), policy=policy, retry_unknown=True
    )
    assert successor.attempt_no == 2 and successor.attempt_id != token.attempt_id
    assert not finish(token, DeliveryResult.ACCEPTED, now=token.lease_until + timedelta(seconds=7))
    assert finish(successor, DeliveryResult.ACCEPTED, now=token.lease_until + timedelta(seconds=7))


def test_orphaned_processing_record_is_quarantined_as_unknown(source):
    message = source[2]
    OutboxMessage.objects.filter(pk=message.pk).update(status="processing", lease_until=NOW)
    with transaction.atomic():
        assert recover_expired(policy=POLICY, now=NOW) == 1
    attempt = DeliveryAttempt.objects.get()
    assert attempt.result == "unknown" and attempt.error_code == DeliveryError.ORPHANED.value
    assert claim(now=NOW + DAY) is None


def test_crash_after_external_acceptance_preserves_uncertainty_until_recovery(source):
    class CrashAfterAcceptance(MemoryTransport):
        def send(self, message):
            super().send(message)
            raise SystemExit("Caída sintética después de aceptar.")

    transport = CrashAfterAcceptance()
    with pytest.raises(SystemExit):
        worker(transport).run_once(operation=context())
    assert len(transport.messages) == 1 and DeliveryAttempt.objects.get().result == "running"
    outcome = worker().run_once(operation=context(NOW + timedelta(seconds=61)))
    assert outcome.recovered == 1 and outcome.status == "empty"
    assert DeliveryAttempt.objects.get().result == "unknown"


@pytest.mark.parametrize("mode", ["expire_source", "expire_lease", "exception", "wrong_return"])
def test_rendering_cannot_bypass_expiry_or_leak_errors(source, mode):
    class Clock:
        instant = NOW

        def now(self):
            return self.instant

    clock = Clock()
    if mode == "expire_source":
        EmailChallenge.objects.filter(pk=source[1].pk).update(expires_at=NOW + timedelta(seconds=1))

    def render(ctx):
        if mode == "exception":
            raise RuntimeError("private-token-in-error")
        if mode == "wrong_return":
            return "private-body"
        clock.instant = NOW + timedelta(seconds=2 if mode == "expire_source" else 61)
        return RenderedEmail("Asunto", "Texto")

    transport = MemoryTransport()
    result = worker(transport, templates=(email_template(render),)).run_once(
        operation=OperationContext.start(clock=clock)
    )
    assert not transport.messages
    assert result.status == (
        "stale" if mode == "expire_lease" else "cancelled" if mode == "expire_source" else "failed"
    )
    assert "private" not in (DeliveryAttempt.objects.get().error_code or "")


def session_pid():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'")
        cursor.execute("SET LOCAL statement_timeout='10s'")
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def test_two_claimers_skip_locked_row_and_never_share_claim(source):
    barrier = Barrier(2)
    held, release = Event(), Event()

    def first():
        try:
            with transaction.atomic():
                pid = session_pid()
                token = claim_next(policy=POLICY, now=NOW)
                held.set()
                barrier.wait(timeout=5)
                assert release.wait(timeout=5)
                return token, pid
        finally:
            connections.close_all()

    def second():
        try:
            assert held.wait(timeout=5)
            with transaction.atomic():
                pid = session_pid()
                barrier.wait(timeout=5)
                token = claim_next(policy=POLICY, now=NOW)
            release.set()
            return token, pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(first), pool.submit(second)
        one, two = a.result(timeout=15), b.result(timeout=15)
    assert one[0] is not None and two[0] is None and one[1] != two[1]
    assert DeliveryAttempt.objects.count() == 1


def test_cli_emits_only_counters_and_rejects_invalid_limit(source):
    output = StringIO()
    call_command("deliver_outbox", limit=1, stdout=output)
    assert "failed" in output.getvalue() and "example.invalid" not in output.getvalue()
    assert "token" not in output.getvalue() and "synthetic.confirmation" not in output.getvalue()
    with pytest.raises(CommandError, match="límite"):
        call_command("deliver_outbox", limit=0)


def notice_source(organization=False):
    account = Account.objects.create_user(f"notice-{uuid4()}@example.invalid")
    org = None
    if organization:
        org = Organization.objects.create(
            name="Entidad sintética", kind="private", created_by=account
        )
        OrganizationVerification.objects.create(
            organization=org,
            requested_by=account,
            status="approved",
            decided_by=account,
            decided_at=NOW - DAY,
            decision_reason="Evidencia sintética",
        )
        Representation.objects.create(
            organization=org, account=account, granted_by=account, created_at=NOW - DAY
        )
    opportunity = Opportunity.objects.create(
        owner_account=None if org else account,
        owner_organization=org,
        author=account,
        title="Oportunidad sintética",
        description="Descripción",
        area="Área",
        responsible_label="Responsable",
        lifecycle="active",
        published_at=NOW - DAY,
        expires_at=NOW + DAY,
        validity_revision=1,
    )
    LifecycleEvent.objects.create(
        opportunity=opportunity,
        validity_revision=1,
        event_kind="publish",
        actor=account,
        from_state="draft",
        to_state="active",
        new_expires_at=NOW + DAY,
    )
    notice = Notice.objects.create(
        opportunity=opportunity,
        validity_revision=1,
        scheduled_for=NOW - timedelta(seconds=1),
        channel="email",
    )
    message = OutboxMessage.objects.create(
        notice=notice,
        recipient_account=account,
        channel="email",
        destination=account.email,
        template_key="synthetic.notice",
        payload={
            "notice_id": str(notice.pk),
            "opportunity_id": str(opportunity.pk),
            "validity_revision": 1,
        },
        idempotency_key=f"synthetic:{uuid4()}",
        available_at=NOW,
    )
    return account, org, opportunity, notice, message


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "cancelled",
        "revision",
        "closed",
        "hidden",
        "expired",
        "future",
        "foreign",
        "payload",
    ],
)
def test_notice_rechecks_revision_visibility_validity_recipient_and_schedule(change):
    account, org, opportunity, notice, message = notice_source()
    if change == "cancelled":
        Notice.objects.filter(pk=notice.pk).update(cancelled_at=NOW)
    if change == "revision":
        Opportunity.objects.filter(pk=opportunity.pk).update(validity_revision=2)
    if change == "closed":
        Opportunity.objects.filter(pk=opportunity.pk).update(lifecycle="closed")
    if change == "hidden":
        Opportunity.objects.filter(pk=opportunity.pk).update(visibility="hidden")
    if change == "expired":
        Opportunity.objects.filter(pk=opportunity.pk).update(expires_at=NOW)
    if change == "future":
        Notice.objects.filter(pk=notice.pk).update(scheduled_for=NOW + DAY)
    if change == "foreign":
        Opportunity.objects.filter(pk=opportunity.pk).update(
            owner_account=Account.objects.create_user("not-author@example.invalid")
        )
    if change == "payload":
        OutboxMessage.objects.filter(pk=message.pk).update(payload={"token": "private"})
    transport = MemoryTransport()
    template = DeliveryTemplate(
        "synthetic.notice", "notice", lambda ctx: RenderedEmail("Recordatorio", "Texto sintético")
    )
    result = worker(transport, templates=(template,)).run_once(operation=context())
    assert result.status == (
        "accepted" if change == "none" else "failed" if change == "payload" else "cancelled"
    )
    assert len(transport.messages) == (1 if change == "none" else 0)


@pytest.mark.parametrize("change", ["none", "revoked", "unverified"])
def test_organization_notice_requires_current_representative_and_verified_entity(change):
    account, org, opportunity, notice, message = notice_source(organization=True)
    if change == "revoked":
        Representation.objects.filter(organization=org).update(revoked_at=NOW, revoked_by=account)
    if change == "unverified":
        OrganizationVerification.objects.filter(organization=org).update(status="withdrawn")
    transport = MemoryTransport()
    template = DeliveryTemplate(
        "synthetic.notice", "notice", lambda ctx: RenderedEmail("Aviso", "Texto")
    )
    result = worker(transport, templates=(template,)).run_once(operation=context())
    assert result.status == ("accepted" if change == "none" else "cancelled")
    assert len(transport.messages) == (1 if change == "none" else 0)


def test_two_runners_cannot_send_same_unexpired_claim(source):
    entered, release = Event(), Event()
    transport_pids = []

    class BlockingTransport(MemoryTransport):
        def send(self, message):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                transport_pids.append(cursor.fetchone()[0])
            entered.set()
            assert release.wait(timeout=8)
            return super().send(message)

    transport = BlockingTransport()

    def first():
        try:
            return worker(transport).run_once(operation=context())
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert entered.wait(timeout=5)
            assert worker(transport).run_once(operation=context()).status == "empty"
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                assert cursor.fetchone()[0] != transport_pids[0]
        finally:
            release.set()
        assert future.result(timeout=10).status == "accepted"
    assert len(transport.messages) == 1 and DeliveryAttempt.objects.count() == 1


def test_two_recoverers_skip_same_expired_claim(source):
    token = claim()
    held, release = Event(), Event()

    def first():
        try:
            with transaction.atomic():
                pid = session_pid()
                count = recover_expired(policy=POLICY, now=token.lease_until)
                held.set()
                assert release.wait(timeout=8)
            return count, pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert held.wait(timeout=5)
            with transaction.atomic():
                pid = session_pid()
                assert recover_expired(policy=POLICY, now=token.lease_until) == 0
        finally:
            release.set()
        count, other_pid = future.result(timeout=10)
    assert count == 1 and pid != other_pid
    assert (
        DeliveryAttempt.objects.count() == 1 and DeliveryAttempt.objects.get().result == "unknown"
    )


@pytest.mark.parametrize("change", ["inactive", "expired"])
def test_origin_is_revalidated_after_waiting_for_account_lock(source, change):
    account, challenge, message = source
    if change == "expired":
        EmailChallenge.objects.filter(pk=challenge.pk).update(expires_at=NOW + timedelta(seconds=1))
    held, release = Event(), Event()
    waiter_pid = Queue()
    transport = MemoryTransport()

    class Clock:
        instant = NOW

        def now(self):
            return self.instant

    clock = Clock()

    def holder():
        try:
            with transaction.atomic():
                pid = session_pid()
                Account.objects.select_for_update().get(pk=account.pk)
                held.set()
                assert release.wait(timeout=8)
                if change == "inactive":
                    Account.objects.filter(pk=account.pk).update(is_active=False)
            return pid
        finally:
            connections.close_all()

    def waiter():
        try:
            assert held.wait(timeout=5)
            # Publica PID sin envolver al ejecutor en una transacción exterior.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                waiter_pid.put(cursor.fetchone()[0])
            return worker(transport).run_once(operation=OperationContext.start(clock=clock))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(holder), pool.submit(waiter)
        pid = waiter_pid.get(timeout=5)
        try:
            deadline = monotonic() + 5
            blocking = []
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [pid])
                    blocking = cursor.fetchone()[0]
                if blocking:
                    break
                Event().wait(0.01)
            assert blocking
            clock.instant = NOW + timedelta(seconds=2)
        finally:
            release.set()
        assert a.result(timeout=10) != pid
        assert b.result(timeout=10).status == "cancelled"
    assert not transport.messages
    assert DeliveryAttempt.objects.get().error_code == DeliveryError.SOURCE_INVALID.value


def test_claim_failure_rolls_back_attempt_and_processing_state(source, monkeypatch):
    original = delivery_commands.claim_next

    def fail_after_claim(**kwargs):
        original(**kwargs)
        raise RuntimeError("Fallo sintético antes del commit de reclamación.")

    monkeypatch.setattr(delivery_commands, "claim_next", fail_after_claim)
    with pytest.raises(RuntimeError):
        worker().run_once(operation=context())
    source[2].refresh_from_db()
    assert source[2].status == "pending" and not DeliveryAttempt.objects.exists()


def test_commit_failure_after_transport_acceptance_is_recovered_as_unknown(source, monkeypatch):
    original = delivery_commands.finish_claim

    def fail_after_finish(**kwargs):
        original(**kwargs)
        raise RuntimeError("Fallo sintético al guardar el resultado.")

    transport = MemoryTransport()
    with monkeypatch.context() as patch:
        patch.setattr(delivery_commands, "finish_claim", fail_after_finish)
        with pytest.raises(RuntimeError):
            worker(transport).run_once(operation=context())
    assert len(transport.messages) == 1
    source[2].refresh_from_db()
    assert source[2].status == "processing" and DeliveryAttempt.objects.get().result == "running"
    result = worker(transport).run_once(operation=context(NOW + timedelta(seconds=61)))
    assert result.recovered == 1 and result.status == "empty"
    assert DeliveryAttempt.objects.get().result == "unknown" and len(transport.messages) == 1
