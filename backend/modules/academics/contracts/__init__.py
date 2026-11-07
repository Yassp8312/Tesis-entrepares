"""Tipos de intercambio de M03; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PersonalVerificationState:
    account_id: UUID
    is_verified: bool
