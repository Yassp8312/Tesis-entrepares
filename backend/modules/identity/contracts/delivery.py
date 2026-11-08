from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ChallengeDeliveryState:
    challenge_id: UUID
    account_id: UUID
    purpose: str
    key_version: str
    expires_at: datetime
    consumed_at: datetime | None
    invalidated_at: datetime | None
    email_snapshot: str = field(repr=False)
