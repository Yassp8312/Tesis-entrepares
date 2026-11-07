"""Lecturas propietarias de M02; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from django.db import connection

from modules.profiles.contracts import ProfileCompletenessState


def get_profile_completeness(*, profile_id: UUID) -> ProfileCompletenessState | None:
    """Consulta el hecho derivado actual; application autoriza el uso de esta proyección."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT profile_id, account_id, is_complete FROM model_profile_completeness WHERE profile_id = %s",
            [profile_id],
        )
        row = cursor.fetchone()
    return ProfileCompletenessState(*row) if row is not None else None
