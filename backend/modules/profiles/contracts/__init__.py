"""Tipos de intercambio de M02; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProfileCompletenessState:
    profile_id: UUID
    account_id: UUID
    is_complete: bool
