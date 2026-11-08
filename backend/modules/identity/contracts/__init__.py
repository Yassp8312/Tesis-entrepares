"""Tipos de intercambio de M01; no devuelven modelos ORM ni credenciales."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

CONFIRMATION_EXAMPLE_KEY_VERSION = "sample-only"


@dataclass(frozen=True, slots=True)
class AccountState:
    """Estado técnico mínimo; no acredita verificación personal ni capacidades M08."""

    account_id: UUID
    is_active: bool


@dataclass(frozen=True, slots=True)
class LockedAccountState:
    """Proyección privada bajo bloqueo; no es un permiso ni salida HTTP."""

    account_id: UUID
    is_active: bool
    email: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ConfirmationState:
    challenge_id: UUID
    account_id: UUID
    purpose: str
    expires_at: datetime
    consumed_at: datetime | None
    invalidated_at: datetime | None
    key_version: str


class ConfirmationConflict(Exception):
    """El recurso ya no admite la transición del ejemplo; no incluye datos privados."""
