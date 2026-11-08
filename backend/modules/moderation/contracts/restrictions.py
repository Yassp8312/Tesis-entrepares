"""Hechos actuales mínimos de M07 para autorización interna, sin motivos privados."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RestrictionState:
    account_id: UUID
    capability_code: str
    context: str
    starts_at: datetime
    ends_at: datetime | None
    revoked_at: datetime | None
    is_ban: bool
