from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OpportunityDeliveryState:
    opportunity_id: UUID
    owner_account_id: UUID | None
    owner_organization_id: UUID | None
    lifecycle: str
    visibility: str
    published_at: datetime | None
    expires_at: datetime | None
    validity_revision: int
