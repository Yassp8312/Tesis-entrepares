"""Lecturas propietarias de M05; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from django.db import connection

from modules.opportunities.contracts import OpportunityFundingState


def get_opportunity_funding(*, opportunity_id: UUID) -> OpportunityFundingState | None:
    """Deriva la financiación de T21 sin devolver el monto o el contenido del proyecto."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT opportunity_id, is_funded FROM model_opportunity_funding WHERE opportunity_id = %s",
            [opportunity_id],
        )
        row = cursor.fetchone()
    return OpportunityFundingState(*row) if row is not None else None
