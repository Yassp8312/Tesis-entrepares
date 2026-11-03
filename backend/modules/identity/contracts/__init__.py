"""Tipos de intercambio de M01; no devuelven modelos ORM ni credenciales."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AccountState:
    """Estado técnico mínimo; no acredita verificación personal ni capacidades M08."""

    account_id: UUID
    is_active: bool
