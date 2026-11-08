"""Escrituras propietarias de M09; application coordina los casos y transacciones."""

from uuid import UUID

from django.core.validators import validate_email
from django.db import connection

from core.correlation import OperationContext
from modules.notifications.contracts import (
    CONFIRMATION_EXAMPLE_TEMPLATE,
    ConfirmationExampleIntent,
    ConfirmationOutboxConflict,
    ConfirmationOutboxState,
)
from modules.notifications.models import OutboxMessage
from modules.notifications.selectors import lock_confirmation_outbox


def enqueue_confirmation_example(
    *, intent: ConfirmationExampleIntent, operation: OperationContext
) -> ConfirmationOutboxState:
    """Intención de muestra sin token o enlace utilizable, no ejecuta transporte."""
    if type(intent) is not ConfirmationExampleIntent or not isinstance(operation, OperationContext):
        raise TypeError("La salida requiere una intención y un contexto explícitos.")
    intent.__post_init__()
    validate_email(intent.destination)
    if not connection.in_atomic_block:
        raise RuntimeError("La salida requiere la transacción del coordinador.")
    message = OutboxMessage.objects.create(
        challenge_id=intent.challenge_id,
        recipient_account_id=intent.recipient_account_id,
        channel="email",
        destination=intent.destination,
        template_key=CONFIRMATION_EXAMPLE_TEMPLATE,
        payload={"challenge_id": str(intent.challenge_id)},
        idempotency_key=f"transaction_sample.confirmation:{intent.challenge_id}",
        available_at=operation.now(),
    )
    return ConfirmationOutboxState(
        message.pk, intent.challenge_id, message.status, message.template_key
    )


def cancel_confirmation_example(
    *, challenge_id: UUID, operation: OperationContext
) -> tuple[UUID, ...]:
    """Solo salidas de muestra pendientes; conflicto antes de modificar un lote incompleto."""
    if not isinstance(operation, OperationContext):
        raise TypeError("La cancelación requiere un contexto explícito.")
    messages = lock_confirmation_outbox(challenge_id=challenge_id)
    if not messages or any(
        item.template_key != CONFIRMATION_EXAMPLE_TEMPLATE
        or item.status not in (OutboxMessage.Status.PENDING, OutboxMessage.Status.CANCELLED)
        for item in messages
    ):
        raise ConfirmationOutboxConflict("La salida ya no admite la transición de muestra.")
    pending_ids = tuple(
        item.message_id for item in messages if item.status == OutboxMessage.Status.PENDING
    )
    OutboxMessage.objects.filter(pk__in=pending_ids).update(
        status=OutboxMessage.Status.CANCELLED, updated_at=operation.now()
    )
    return pending_ids
