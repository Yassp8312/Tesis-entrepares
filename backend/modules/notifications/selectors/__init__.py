"""Lecturas propietarias de M09; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from django.db import connection

from modules.notifications.contracts import ConfirmationOutboxState
from modules.notifications.models import OutboxMessage


def lock_confirmation_outbox(*, challenge_id: UUID) -> tuple[ConfirmationOutboxState, ...]:
    """Después de cuenta/comprobación, bloquea las salidas en orden UUID ascendente."""
    if not isinstance(challenge_id, UUID):
        raise TypeError("Se requiere una referencia interna de comprobación.")
    if not connection.in_atomic_block:
        raise RuntimeError("La salida requiere la transacción del coordinador.")
    rows = (
        OutboxMessage.objects.filter(challenge_id=challenge_id)
        .order_by("pk")
        .select_for_update(of=("self",))
        .values_list("id", "challenge_id", "status", "template_key")
    )
    return tuple(ConfirmationOutboxState(*row) for row in rows)
