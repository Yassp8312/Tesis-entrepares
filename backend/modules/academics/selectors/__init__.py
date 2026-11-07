"""Lecturas propietarias de M03; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from django.db import connection

from modules.academics.contracts import PersonalVerificationState


def get_personal_verification(*, account_id: UUID) -> PersonalVerificationState | None:
    """Lee respaldos aprobados almacenados; no concede una autorización del caso."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT account_id, is_verified FROM model_personal_verification WHERE account_id = %s",
            [account_id],
        )
        row = cursor.fetchone()
    return PersonalVerificationState(*row) if row is not None else None
