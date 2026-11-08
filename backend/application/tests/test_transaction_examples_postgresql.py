"""T14: coordinación, rollback y bloqueos de muestra sobre PostgreSQL real."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from queue import Queue
from threading import Barrier, Event
from time import monotonic
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, connections, transaction

from application.examples import confirmation as examples
from core.clock import FixedClock
from core.correlation import OperationContext
from modules.access.contracts import Action, DecisionCode
from modules.access.models import Capability
from modules.audit import commands as audit_commands
from modules.audit.models import AuditEvent
from modules.identity import commands as identity_commands
from modules.identity.contracts import ConfirmationConflict
from modules.identity.models import Account, EmailChallenge
from modules.identity.selectors import lock_account_states
from modules.moderation.models import Decision, Measure, Report, Restriction
from modules.notifications import commands as notification_commands
from modules.notifications.contracts import (
    CONFIRMATION_EXAMPLE_TEMPLATE,
    ConfirmationOutboxConflict,
)
from modules.notifications.models import OutboxMessage
from modules.profiles.models import Profile
from modules.publications.models import Publication

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
DAY = timedelta(days=1)


@pytest.fixture
def account():
    return Account.objects.create_user("transaction-synthetic@example.invalid")


def operation(instant=NOW):
    return OperationContext.start(clock=FixedClock(instant))


def prepare(account_id, **changes):
    values = dict(
        actor_account_id=account_id,
        account_id=account_id,
        expires_at=NOW + DAY,
        operation=operation(),
    )
    return examples.prepare_confirmation_example(**{**values, **changes})


def cancel(account_id, challenge_id, **changes):
    values = dict(
        actor_account_id=account_id,
        account_id=account_id,
        challenge_id=challenge_id,
        operation=operation(),
    )
    return examples.cancel_confirmation_example(**{**values, **changes})


def snapshot():
    return tuple(
        tuple(model.objects.order_by("pk").values())
        for model in (EmailChallenge, AuditEvent, OutboxMessage)
    )


def test_prepare_persists_three_owners_and_minimal_correlated_evidence(account, monkeypatch):
    def unexpected_transport(*args, **kwargs):
        raise AssertionError("El ejemplo no debe ejecutar correo.")

    monkeypatch.setattr("django.core.mail.send_mail", unexpected_transport)
    context = operation()
    result = prepare(account.pk, operation=context)
    challenge = EmailChallenge.objects.get(pk=result.challenge_id)
    audit = AuditEvent.objects.get(pk=result.audit_event_id)
    message = OutboxMessage.objects.get(pk=result.outbox_ids[0])
    assert challenge.account_id == account.pk and challenge.email_snapshot == account.email
    assert challenge.purpose == "email_confirmation" and challenge.created_at == NOW
    assert challenge.key_version == "sample-only"
    assert challenge.expires_at == NOW + DAY
    assert challenge.consumed_at is None and challenge.invalidated_at is None
    assert audit.correlation_id == result.correlation_id == context.correlation_id
    assert audit.actor_account_id == account.pk and audit.resource_id == challenge.pk
    assert audit.action_code == Action.CONFIRMATION_SAMPLE_PREPARE.value
    assert audit.before_state is None and audit.after_state == {"status": "pending"}
    assert message.challenge_id == challenge.pk and message.recipient_account_id == account.pk
    assert message.destination == account.email and message.status == "pending"
    assert message.template_key == CONFIRMATION_EXAMPLE_TEMPLATE
    assert message.payload == {"challenge_id": str(challenge.pk)}
    assert message.available_at == NOW and message.lease_until is None and message.sent_at is None
    assert not Profile.objects.exists()
    account.refresh_from_db()
    assert account.last_login is None and not account.is_staff and not account.is_superuser


def test_cancel_preserves_source_and_initial_event_and_changes_only_its_pending_messages(account):
    initial = prepare(account.pk)
    unrelated = prepare(account.pk)
    context = operation(NOW + timedelta(minutes=5))
    result = cancel(account.pk, initial.challenge_id, operation=context)
    challenge = EmailChallenge.objects.get(pk=initial.challenge_id)
    message = OutboxMessage.objects.get(pk=initial.outbox_ids[0])
    audit = AuditEvent.objects.get(pk=result.audit_event_id)
    assert challenge.invalidated_at == context.now() and challenge.consumed_at is None
    assert message.status == "cancelled" and message.updated_at == context.now()
    assert result.outbox_ids == initial.outbox_ids
    assert audit.correlation_id == context.correlation_id
    assert audit.before_state == {"status": "pending"} and audit.after_state == {
        "status": "cancelled"
    }
    assert AuditEvent.objects.filter(pk=initial.audit_event_id).exists()
    assert OutboxMessage.objects.get(pk=unrelated.outbox_ids[0]).status == "pending"
    assert EmailChallenge.objects.get(pk=unrelated.challenge_id).invalidated_at is None


@pytest.mark.parametrize("stage", ["identity", "audit", "outbox"])
@pytest.mark.parametrize("mode", ["prepare", "cancel"])
def test_failure_after_each_owner_write_rolls_back_entire_case(account, monkeypatch, stage, mode):
    initial = prepare(account.pk) if mode == "cancel" else None
    before = snapshot()
    bindings = {
        ("prepare", "identity"): (identity_commands, "create_confirmation_example"),
        ("prepare", "audit"): (audit_commands, "append_event"),
        ("prepare", "outbox"): (notification_commands, "enqueue_confirmation_example"),
        ("cancel", "identity"): (identity_commands, "invalidate_confirmation_example"),
        ("cancel", "audit"): (audit_commands, "append_event"),
        ("cancel", "outbox"): (notification_commands, "cancel_confirmation_example"),
    }
    module, name = bindings[(mode, stage)]
    original = getattr(module, name)

    def fail_after_write(**kwargs):
        original(**kwargs)
        raise RuntimeError("Fallo sintético después de escribir.")

    monkeypatch.setattr(module, name, fail_after_write)
    with pytest.raises(RuntimeError, match="Fallo sintético"):
        prepare(account.pk) if mode == "prepare" else cancel(account.pk, initial.challenge_id)
    assert snapshot() == before


def test_real_integrity_error_does_not_leave_business_audit_or_first_outbox(account, monkeypatch):
    original = notification_commands.enqueue_confirmation_example

    def duplicate(**kwargs):
        original(**kwargs)
        return original(**kwargs)

    monkeypatch.setattr(notification_commands, "enqueue_confirmation_example", duplicate)
    before = snapshot()
    with pytest.raises(IntegrityError) as error:
        prepare(account.pk)
    assert error.value.__cause__.diag.constraint_name == "uq_t35_key01"
    assert snapshot() == before


@pytest.mark.parametrize("mode", ["prepare", "cancel"])
def test_outer_transaction_can_revert_successful_inner_case(account, mode):
    initial = prepare(account.pk) if mode == "cancel" else None
    before = snapshot()
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            prepare(account.pk) if mode == "prepare" else cancel(account.pk, initial.challenge_id)
            raise RuntimeError("Rollback de la transacción exterior.")
    assert snapshot() == before


@pytest.mark.parametrize("change", ["inactive", "foreign", "unknown", "superuser_foreign"])
def test_current_identity_and_ownership_are_checked_before_writes(account, change):
    other = Account.objects.create_user("another-transaction@example.invalid")
    target = account.pk
    if change == "inactive":
        Account.objects.filter(pk=account.pk).update(is_active=False)
    elif change in ("foreign", "superuser_foreign"):
        target = other.pk
    else:
        target = uuid4()
    if change == "superuser_foreign":
        Account.objects.filter(pk=account.pk).update(is_staff=True, is_superuser=True)
    before = snapshot()
    with pytest.raises(examples.ExampleAccessDenied) as error:
        prepare(target, actor_account_id=account.pk)
    assert account.email not in str(error.value)
    assert snapshot() == before


@pytest.mark.parametrize("expires", [NOW, NOW - DAY])
def test_creation_rejects_expired_deadline_without_writes(account, expires):
    before = snapshot()
    with pytest.raises(ConfirmationConflict):
        prepare(account.pk, expires_at=expires)
    assert snapshot() == before


@pytest.mark.parametrize(
    "change", ["consumed", "invalidated", "expired", "purpose", "key", "foreign", "missing"]
)
def test_cancel_rechecks_challenge_state_and_exact_owner(account, change):
    initial = prepare(account.pk)
    challenge_id = initial.challenge_id
    changes = {}
    if change == "consumed":
        changes = {"consumed_at": NOW}
    elif change == "invalidated":
        changes = {"invalidated_at": NOW}
    elif change == "expired":
        changes = {"created_at": NOW - 2 * DAY, "expires_at": NOW}
    elif change == "purpose":
        changes = {"purpose": "password_reset"}
    elif change == "key":
        changes = {"key_version": "v1"}
    elif change == "foreign":
        changes = {"account": Account.objects.create_user("foreign-challenge@example.invalid")}
    else:
        challenge_id = uuid4()
    EmailChallenge.objects.filter(pk=initial.challenge_id).update(**changes) if changes else None
    before = snapshot()
    with pytest.raises(ConfirmationConflict):
        cancel(account.pk, challenge_id)
    assert snapshot() == before


@pytest.mark.parametrize("change", ["processing", "sent", "failed", "template", "missing"])
def test_incompatible_outbox_aborts_invalidation_and_new_audit(account, change):
    initial = prepare(account.pk)
    messages = OutboxMessage.objects.filter(pk=initial.outbox_ids[0])
    if change == "missing":
        messages.delete()
    elif change == "template":
        messages.update(template_key="real.flow.not_sample")
    else:
        messages.update(
            status=change,
            lease_until=NOW + DAY if change == "processing" else None,
            sent_at=NOW if change == "sent" else None,
        )
    before = snapshot()
    with pytest.raises(ConfirmationOutboxConflict):
        cancel(account.pk, initial.challenge_id)
    assert snapshot() == before


def test_mixed_pending_and_incompatible_batch_is_not_partially_cancelled(account):
    initial = prepare(account.pk)
    source = OutboxMessage.objects.get(pk=initial.outbox_ids[0])
    source.pk = uuid4()
    source.idempotency_key = "synthetic-second-message"
    source.status = "failed"
    source.save(force_insert=True)
    before = snapshot()
    with pytest.raises(ConfirmationOutboxConflict):
        cancel(account.pk, initial.challenge_id)
    assert snapshot() == before


def add_restriction(account, action, starts_at=NOW - DAY):
    publication = Publication.objects.create(
        kind="news",
        title="Publicación sintética",
        body="Prueba",
        owner_account=account,
        author=account,
    )
    report = Report.objects.create(
        reported_by=account, publication=publication, reason="Motivo sintético"
    )
    decision = Decision.objects.create(
        report=report,
        decided_by=account,
        outcome="violation",
        reason="Decisión sintética",
        content_action="none",
    )
    measure = Measure.objects.create(
        account=account, source_decision=decision, kind="ban", starts_at=starts_at
    )
    cap = Capability.objects.create(code=action.value, description="Capacidad sintética")
    Restriction.objects.create(measure=measure, capability=cap, context_kind="personal")


@pytest.mark.parametrize("matching", [True, False])
def test_authorization_loads_current_moderation_facts_without_inventing_pending_policy(
    account, matching
):
    action = Action.CONFIRMATION_SAMPLE_PREPARE if matching else Action.CONFIRMATION_SAMPLE_CANCEL
    add_restriction(account, action)
    before = snapshot()
    if matching:
        with pytest.raises(examples.ExampleAccessDenied) as error:
            prepare(account.pk)
        assert error.value.decision.code is DecisionCode.CONDITION_REQUIRED
        assert snapshot() == before
    else:
        assert prepare(account.pk)


def worker_session():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'")
        cursor.execute("SET LOCAL statement_timeout='10s'")
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def wait_until_blocked(pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", [pid])
            if cursor.fetchone()[0]:
                return
        Event().wait(0.01)
    raise AssertionError("La segunda conexión debe haber esperado un bloqueo real.")


@pytest.mark.django_db(transaction=True)
def test_new_temporal_restriction_is_rechecked_after_waiting_for_outbox(account):
    initial = prepare(account.pk)
    add_restriction(account, Action.CONFIRMATION_SAMPLE_CANCEL, starts_at=NOW + timedelta(hours=1))
    held, release = Event(), Event()
    waiter_pid = Queue()

    class AdjustableClock:
        instant = NOW

        def now(self):
            return self.instant

    clock = AdjustableClock()

    def holder():
        try:
            with transaction.atomic():
                pid = worker_session()
                OutboxMessage.objects.select_for_update().get(pk=initial.outbox_ids[0])
                held.set()
                assert release.wait(timeout=8)
            return pid
        finally:
            connections.close_all()

    def waiter():
        try:
            assert held.wait(timeout=5)
            with transaction.atomic():
                waiter_pid.put(worker_session())
                try:
                    cancel(
                        account.pk,
                        initial.challenge_id,
                        operation=OperationContext.start(clock=clock),
                    )
                    return "unexpected_commit"
                except examples.ExampleAccessDenied:
                    return "denied"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(holder), pool.submit(waiter)
        pid = waiter_pid.get(timeout=5)
        try:
            wait_until_blocked(pid)
            clock.instant = NOW + timedelta(hours=2)
        finally:
            release.set()
        assert first.result(timeout=10) != pid
        assert second.result(timeout=10) == "denied"
    assert EmailChallenge.objects.get(pk=initial.challenge_id).invalidated_at is None
    assert OutboxMessage.objects.get(pk=initial.outbox_ids[0]).status == "pending"
    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_cancellations_are_serialized_and_only_one_transition_commits(account):
    initial = prepare(account.pk)
    barrier = Barrier(2)

    def worker():
        try:
            with transaction.atomic():
                pid = worker_session()
                barrier.wait(timeout=5)
                try:
                    cancel(account.pk, initial.challenge_id)
                    return "cancelled", pid
                except ConfirmationConflict:
                    return "conflict", pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(result[0] for result in results) == ["cancelled", "conflict"]
    assert len({result[1] for result in results}) == 2
    assert (
        AuditEvent.objects.filter(action_code=Action.CONFIRMATION_SAMPLE_CANCEL.value).count() == 1
    )
    assert OutboxMessage.objects.get(pk=initial.outbox_ids[0]).status == "cancelled"


@pytest.mark.django_db(transaction=True)
def test_opposite_input_order_uses_same_account_lock_order(account):
    other = Account.objects.create_user("lock-order-synthetic@example.invalid")
    barrier = Barrier(2)

    def worker(ids):
        try:
            with transaction.atomic():
                pid = worker_session()
                barrier.wait(timeout=5)
                locked = lock_account_states(account_ids=ids)
                return tuple(item.account_id for item in locked), pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, ids) for ids in ((account.pk, other.pk), (other.pk, account.pk))
        ]
        results = [future.result(timeout=15) for future in futures]
    assert results[0][0] == results[1][0] == tuple(sorted((account.pk, other.pk)))
    assert len({result[1] for result in results}) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("change", ["inactive", "expired", "email"])
def test_waiting_case_rechecks_committed_account_and_clock_after_lock(account, change):
    initial = prepare(account.pk)
    held, release = Event(), Event()
    waiter_pid = Queue()

    class AdjustableClock:
        instant = NOW

        def now(self):
            return self.instant

    clock = AdjustableClock()
    context = OperationContext.start(clock=clock)

    def holder():
        try:
            with transaction.atomic():
                pid = worker_session()
                lock_account_states(account_ids=(account.pk,))
                held.set()
                assert release.wait(timeout=8)
                if change == "inactive":
                    Account.objects.filter(pk=account.pk).update(is_active=False)
                if change == "email":
                    Account.objects.filter(pk=account.pk).update(
                        email="changed-under-lock@example.invalid"
                    )
            return pid
        finally:
            connections.close_all()

    def waiter():
        try:
            assert held.wait(timeout=5)
            with transaction.atomic():
                waiter_pid.put(worker_session())
                try:
                    result = (
                        prepare(account.pk, operation=context)
                        if change == "email"
                        else cancel(account.pk, initial.challenge_id, operation=context)
                    )
                    return "ok", result
                except (examples.ExampleAccessDenied, ConfirmationConflict) as error:
                    return type(error).__name__, None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(holder)
        second = pool.submit(waiter)
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
            assert blocking, "La segunda conexión debe haber esperado un bloqueo real."
            if change == "expired":
                clock.instant = NOW + 2 * DAY
        finally:
            release.set()
        holder_pid = first.result(timeout=10)
        outcome, receipt = second.result(timeout=10)
    assert holder_pid != pid
    if change == "email":
        assert outcome == "ok"
        assert (
            EmailChallenge.objects.get(pk=receipt.challenge_id).email_snapshot
            == "changed-under-lock@example.invalid"
        )
        assert (
            OutboxMessage.objects.get(pk=receipt.outbox_ids[0]).destination
            == "changed-under-lock@example.invalid"
        )
    else:
        assert outcome == (
            "ExampleAccessDenied" if change == "inactive" else "ConfirmationConflict"
        )
        assert EmailChallenge.objects.get(pk=initial.challenge_id).invalidated_at is None
        assert OutboxMessage.objects.get(pk=initial.outbox_ids[0]).status == "pending"
        assert AuditEvent.objects.count() == 1
