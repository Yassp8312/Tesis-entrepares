from django.db import connection

from modules.organizations.models import Organization, Representation
from modules.organizations.selectors import get_organization_verification


def lock_delivery_organization(*, organization_id, account_id, now) -> bool:
    """Ancla de entidad antes de oportunidad/salida; no concede respaldo personal."""
    if not connection.in_atomic_block:
        raise RuntimeError("La entidad requiere la transacción del coordinador.")
    row = (
        Organization.objects.filter(pk=organization_id)
        .select_for_update()
        .values_list("id", flat=True)
        .first()
    )
    if row is None:
        return False
    state = get_organization_verification(organization_id=row)
    return bool(
        state
        and state.is_verified
        and Representation.objects.filter(
            organization_id=row, account_id=account_id, revoked_at__isnull=True, created_at__lte=now
        ).exists()
    )
