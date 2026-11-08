"""Tipos de intercambio de M09; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass, field
from uuid import UUID

CONFIRMATION_EXAMPLE_TEMPLATE = "transaction_sample.email_confirmation"


@dataclass(frozen=True, slots=True)
class ConfirmationExampleIntent:
    challenge_id: UUID
    recipient_account_id: UUID
    destination: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.challenge_id, UUID) or not isinstance(
            self.recipient_account_id, UUID
        ):
            raise TypeError("La intención requiere referencias internas.")
        if type(self.destination) is not str or not self.destination.strip():
            raise TypeError("La intención requiere un destino privado explícito.")


@dataclass(frozen=True, slots=True)
class ConfirmationOutboxState:
    message_id: UUID
    challenge_id: UUID
    status: str
    template_key: str


class ConfirmationOutboxConflict(Exception):
    """La salida ya no admite la transición del ejemplo; no incluye su destino."""
