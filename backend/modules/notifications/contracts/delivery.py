"""Contratos internos del ejecutor; no admiten cuerpos HTTP o relatos del proveedor."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class DeliveryResult(StrEnum):
    ACCEPTED = "accepted"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


class DeliveryError(StrEnum):
    TEMPORARY = "delivery.temporary"
    PERMANENT = "delivery.permanent"
    UNKNOWN = "delivery.unknown"
    LEASE_EXPIRED = "delivery.lease_expired"
    ORPHANED = "delivery.orphaned"
    SOURCE_INVALID = "delivery.source_invalid"
    TEMPLATE_UNAVAILABLE = "delivery.template_unavailable"
    UNSAFE_PAYLOAD = "delivery.unsafe_payload"
    RENDER_FAILED = "delivery.render_failed"


@dataclass(frozen=True, slots=True)
class WorkerPolicy:
    lease_seconds: int = 120
    max_attempts: int = 3
    retry_seconds: int = 30
    max_retry_seconds: int = 3600
    retry_unknown: bool = False

    def __post_init__(self):
        for value, minimum, maximum in (
            (self.lease_seconds, 10, 86400),
            (self.max_attempts, 1, 100),
            (self.retry_seconds, 1, 86400),
            (self.max_retry_seconds, 1, 604800),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("La política técnica de salida no es válida.")
        if self.max_retry_seconds < self.retry_seconds or type(self.retry_unknown) is not bool:
            raise ValueError("La política técnica de reintento no es válida.")

    def delay(self, attempt_no: int) -> timedelta:
        if type(attempt_no) is not int or attempt_no < 1:
            raise ValueError("Se requiere un número de intento positivo.")
        seconds = min(self.max_retry_seconds, self.retry_seconds * 2 ** min(attempt_no - 1, 30))
        return timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    outbox_id: UUID
    attempt_id: UUID
    attempt_no: int
    lease_until: datetime


@dataclass(frozen=True, slots=True)
class OutboxOrigin:
    outbox_id: UUID
    recipient_account_id: UUID | None
    challenge_id: UUID | None
    notice_id: UUID | None


@dataclass(frozen=True, slots=True)
class OutboxEnvelope:
    origin: OutboxOrigin
    channel: str
    template_key: str = field(repr=False)
    idempotency_key: str = field(repr=False)
    destination: str = field(repr=False)
    payload_json: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class NoticeDeliveryState:
    notice_id: UUID
    opportunity_id: UUID
    validity_revision: int
    scheduled_for: datetime
    channel: str | None
    cancelled_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    """Solo hechos mínimos ya validados; no expone el payload almacenado al renderizador."""

    outbox_id: UUID
    source_id: UUID
    source_kind: str
    purpose: str | None = None
    key_version: str | None = None
    opportunity_id: UUID | None = None
    validity_revision: int | None = None


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str = field(repr=False)
    body: str = field(repr=False)

    def __post_init__(self):
        if (
            type(self.subject) is not str
            or not self.subject.strip()
            or len(self.subject) > 200
            or "\r" in self.subject
            or "\n" in self.subject
            or type(self.body) is not str
            or not self.body.strip()
            or len(self.body) > 200000
        ):
            raise ValueError("El contenido de salida no cumple el contrato.")


@dataclass(frozen=True, slots=True)
class PreparedEmail:
    outbox_id: UUID
    idempotency_key: str = field(repr=False)
    destination: str = field(repr=False)
    content: RenderedEmail = field(repr=False)


@dataclass(frozen=True, slots=True)
class TransportResult:
    result: DeliveryResult
    provider_reference: UUID | None = None

    def __post_init__(self):
        if type(self.result) is not DeliveryResult:
            raise TypeError("Se requiere un resultado explícito del transporte.")
        if self.provider_reference is not None and not isinstance(self.provider_reference, UUID):
            raise TypeError("La referencia del proveedor debe ser un UUID opaco.")


class DeliveryTransport(Protocol):
    supports_idempotency: bool
    timeout_seconds: int

    def send(self, message: PreparedEmail) -> TransportResult: ...
