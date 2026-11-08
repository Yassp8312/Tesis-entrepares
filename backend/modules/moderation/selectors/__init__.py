"""Lecturas propietarias de M07; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from modules.moderation.contracts.restrictions import RestrictionState
from modules.moderation.models import Measure, Restriction


def get_account_restrictions(*, account_id: UUID) -> tuple[RestrictionState, ...]:
    """El coordinador mantiene el ancla de cuenta; M08 evalúa acción, contexto y vigencia."""
    if not isinstance(account_id, UUID):
        raise TypeError("Se requiere una referencia interna de cuenta.")
    rows = (
        Restriction.objects.filter(measure__account_id=account_id)
        .order_by("pk")
        .values_list(
            "capability_id",
            "context_kind",
            "measure__starts_at",
            "measure__ends_at",
            "measure__revoked_at",
            "measure__kind",
        )
    )
    return tuple(
        RestrictionState(account_id, code, context, start, end, revoked, kind == Measure.Kind.BAN)
        for code, context, start, end, revoked, kind in rows
    )
