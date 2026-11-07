"""Tipos de intercambio de M04; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OrganizationVerificationState:
    organization_id: UUID
    is_verified: bool
