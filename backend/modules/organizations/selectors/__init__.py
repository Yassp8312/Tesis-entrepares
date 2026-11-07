"""Lecturas propietarias de M04; devuelve la proyección requerida por el consumidor autorizado."""

from uuid import UUID

from django.db import connection

from modules.organizations.contracts import OrganizationVerificationState


def get_organization_verification(*, organization_id: UUID) -> OrganizationVerificationState | None:
    """Lee el respaldo de la entidad, separado de la persona que la representa."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT organization_id, is_verified FROM model_organization_verification WHERE organization_id = %s",
            [organization_id],
        )
        row = cursor.fetchone()
    return OrganizationVerificationState(*row) if row is not None else None
