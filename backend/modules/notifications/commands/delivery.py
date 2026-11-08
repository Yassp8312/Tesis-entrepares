"""M09 escribe T35/T36 bajo bloqueo propio; application delimita cada commit."""

from datetime import timedelta

from django.db import connection
from django.db.models import OuterRef, Q, Subquery

from core.clock import as_utc
from modules.notifications.contracts.delivery import (
    DeliveryClaim,
    DeliveryError,
    DeliveryResult,
    TransportResult,
    WorkerPolicy,
)
from modules.notifications.models import DeliveryAttempt, OutboxMessage


def _atomic():
    if not connection.in_atomic_block:
        raise RuntimeError("La salida requiere una transacción explícita.")


def _latest(outbox_id):
    return DeliveryAttempt.objects.filter(outbox_id=outbox_id).order_by("-attempt_no").first()


def claim_next(*, policy: WorkerPolicy, now, retry_unknown=False) -> DeliveryClaim | None:
    _atomic()
    now = as_utc(now)
    if type(policy) is not WorkerPolicy or type(retry_unknown) is not bool:
        raise TypeError("La reclamación requiere política técnica explícita.")
    latest = DeliveryAttempt.objects.filter(outbox_id=OuterRef("pk")).order_by("-attempt_no")
    retryable = Q(last_result="failed", last_error=DeliveryError.TEMPORARY.value)
    if retry_unknown and policy.retry_unknown:
        retryable |= Q(last_result="unknown")
    # Pending solo sin intentos previos; FAILED requiere resultado reintentable conocido.
    eligible = Q(status="pending", last_no__isnull=True) | (
        Q(status="failed", last_no__lt=policy.max_attempts) & retryable
    )
    message = (
        OutboxMessage.objects.annotate(
            last_no=Subquery(latest.values("attempt_no")[:1]),
            last_result=Subquery(latest.values("result")[:1]),
            last_error=Subquery(latest.values("error_code")[:1]),
        )
        .filter(eligible, available_at__lte=now)
        .order_by("available_at", "pk")
        .select_for_update(skip_locked=True, of=("self",))
        .first()
    )
    if message is None:
        return None
    attempt_no = (message.last_no or 0) + 1
    lease_until = now + timedelta(seconds=policy.lease_seconds)
    attempt = DeliveryAttempt.objects.create(
        outbox=message,
        attempt_no=attempt_no,
        started_at=now,
    )
    OutboxMessage.objects.filter(pk=message.pk).update(
        status="processing",
        lease_until=lease_until,
        sent_at=None,
        updated_at=now,
    )
    return DeliveryClaim(message.pk, attempt.pk, attempt_no, lease_until)


def _owned_records(*, claim: DeliveryClaim, now):
    """Fencing por UUID/número de intento/plazo: un trabajador antiguo no finaliza otro."""
    _atomic()
    now = as_utc(now)
    if type(claim) is not DeliveryClaim:
        raise TypeError("Se requiere una reclamación interna explícita.")
    message = OutboxMessage.objects.filter(pk=claim.outbox_id).select_for_update().first()
    if (
        message is None
        or message.status != "processing"
        or message.lease_until != claim.lease_until
        or now >= claim.lease_until
    ):
        return None
    attempt = _latest(message.pk)
    if (
        attempt is None
        or attempt.pk != claim.attempt_id
        or attempt.attempt_no != claim.attempt_no
        or attempt.result != "running"
    ):
        return None
    return message, attempt


def lock_claim(*, claim: DeliveryClaim, now) -> bool:
    """Retiene el bloqueo y devuelve solo posesión actual, sin objetos ORM."""
    return _owned_records(claim=claim, now=now) is not None


def finish_claim(
    *,
    claim,
    outcome: TransportResult,
    policy: WorkerPolicy,
    now,
    error: DeliveryError | None = None,
    cancel=False,
) -> bool:
    if (
        type(outcome) is not TransportResult
        or type(policy) is not WorkerPolicy
        or type(cancel) is not bool
    ):
        raise TypeError("El cierre requiere un resultado interno explícito.")
    if error is not None and type(error) is not DeliveryError:
        raise TypeError("El error debe proceder del catálogo técnico.")
    if cancel and outcome.result is DeliveryResult.ACCEPTED:
        raise ValueError("Una cancelación no puede registrar aceptación.")
    owned = _owned_records(claim=claim, now=now)
    if owned is None:
        return False
    message, attempt = owned
    now = as_utc(now)
    if now < attempt.started_at:
        raise ValueError("El reloj no puede terminar un intento antes de iniciarlo.")
    accepted = outcome.result is DeliveryResult.ACCEPTED
    unknown = outcome.result is DeliveryResult.UNKNOWN
    attempt.result = "accepted" if accepted else "unknown" if unknown else "failed"
    attempt.finished_at = now
    attempt.provider_reference = (
        str(outcome.provider_reference) if outcome.provider_reference else None
    )
    attempt.error_code = (
        None
        if accepted
        else (
            error
            or {
                DeliveryResult.TEMPORARY: DeliveryError.TEMPORARY,
                DeliveryResult.PERMANENT: DeliveryError.PERMANENT,
                DeliveryResult.UNKNOWN: DeliveryError.UNKNOWN,
            }[outcome.result]
        ).value
    )
    attempt.save(update_fields=["result", "finished_at", "provider_reference", "error_code"])
    OutboxMessage.objects.filter(pk=message.pk).update(
        status="cancelled" if cancel else "sent" if accepted else "failed",
        sent_at=now if accepted and not cancel else None,
        lease_until=None,
        updated_at=now,
        available_at=now if accepted or cancel else now + policy.delay(attempt.attempt_no),
    )
    return True


def recover_expired(*, policy: WorkerPolicy, now, limit=50) -> int:
    _atomic()
    now = as_utc(now)
    if type(policy) is not WorkerPolicy or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("El lote de recuperación no es válido.")
    messages = list(
        OutboxMessage.objects.filter(status="processing", lease_until__lte=now)
        .order_by("lease_until", "pk")
        .select_for_update(skip_locked=True, of=("self",))[:limit]
    )
    for message in messages:
        attempt = _latest(message.pk)
        if attempt is not None and attempt.result == "running":
            if now < attempt.started_at:
                raise ValueError("El reloj de recuperación es anterior al intento.")
            attempt.result, attempt.finished_at = "unknown", now
            attempt.error_code = DeliveryError.LEASE_EXPIRED.value
            attempt.save(update_fields=["result", "finished_at", "error_code"])
        else:
            # Observación de un registro incompleto; no inventa aceptación del canal.
            attempt = DeliveryAttempt.objects.create(
                outbox=message,
                attempt_no=(attempt.attempt_no if attempt else 0) + 1,
                started_at=now,
                finished_at=now,
                result="unknown",
                error_code=DeliveryError.ORPHANED.value,
            )
        OutboxMessage.objects.filter(pk=message.pk).update(
            status="failed",
            lease_until=None,
            sent_at=None,
            updated_at=now,
            available_at=now + policy.delay(attempt.attempt_no),
        )
    return len(messages)
