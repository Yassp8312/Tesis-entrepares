from django.db import connection

from modules.opportunities.contracts.delivery import OpportunityDeliveryState
from modules.opportunities.models import Opportunity


def get_delivery_owner(*, opportunity_id):
    return (
        Opportunity.objects.filter(pk=opportunity_id)
        .values_list("owner_account_id", "owner_organization_id")
        .first()
    )


def lock_delivery_opportunity(*, opportunity_id) -> OpportunityDeliveryState | None:
    if not connection.in_atomic_block:
        raise RuntimeError("La oportunidad requiere una transacción explícita.")
    row = (
        Opportunity.objects.filter(pk=opportunity_id)
        .select_for_update()
        .values_list(
            "id",
            "owner_account_id",
            "owner_organization_id",
            "lifecycle",
            "visibility",
            "published_at",
            "expires_at",
            "validity_revision",
        )
        .first()
    )
    return OpportunityDeliveryState(*row) if row else None
