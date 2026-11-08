"""Entradas cerradas de M10: no admiten relatos, credenciales ni objetos arbitrarios."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

TECHNICAL_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}")


class ActorKind(StrEnum):
    ACCOUNT = "account"
    SYSTEM = "system"


class ContextKind(StrEnum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"
    SYSTEM = "system"


class AuditState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DRAFT = "draft"
    PUBLISHED = "published"
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    RECOGNIZED = "recognized"
    CANCELLED = "cancelled"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


class AuditReason(StrEnum):
    """Motivo técnico; el relato de decisión permanece en su registro privado de origen."""

    CREATED = "record_created"
    UPDATED = "record_updated"
    APPROVED = "review_approved"
    REJECTED = "review_rejected"
    WITHDRAWN = "backing_withdrawn"
    REVOKED = "authorization_revoked"
    EXPIRED = "validity_expired"
    CLOSED = "record_closed"
    CANCELLED = "record_cancelled"
    REACTIVATED = "record_reactivated"
    EXTENDED = "validity_extended"
    FAILED = "operation_failed"


def require_uuid(value, *, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, UUID):
        raise TypeError("La referencia de auditoría debe ser un UUID.")


@dataclass(frozen=True, slots=True)
class AuditProjection:
    """Proyección inicial mínima, ampliable explícitamente al integrar cada caso."""

    status: AuditState | None = None
    related_resource_id: UUID | None = None
    revision: int | None = None

    def __post_init__(self):
        if self.status is not None and type(self.status) is not AuditState:
            raise TypeError("El estado de auditoría debe proceder del catálogo cerrado.")
        require_uuid(self.related_resource_id, optional=True)
        if self.revision is not None and (
            type(self.revision) is not int or not 0 <= self.revision <= 2_147_483_647
        ):
            raise ValueError("La revisión de auditoría debe ser un entero admitido.")

    def to_dict(self):
        self.__post_init__()
        result = {}
        if self.status is not None:
            result["status"] = self.status.value
        if self.related_resource_id is not None:
            result["related_resource_id"] = str(self.related_resource_id)
        if self.revision is not None:
            result["revision"] = self.revision
        return result


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Metadatos del servidor; no recibe directamente cuerpos HTTP ni modelos ORM."""

    actor_kind: ActorKind
    context_kind: ContextKind
    action_code: str = field(repr=False)
    resource_kind: str = field(repr=False)
    resource_id: UUID
    actor_account_id: UUID | None = None
    organization_id: UUID | None = None
    academic_scope_id: UUID | None = None
    reason: AuditReason | None = field(default=None, repr=False)
    before_state: AuditProjection | None = field(default=None, repr=False)
    after_state: AuditProjection | None = field(default=None, repr=False)

    def __post_init__(self):
        if type(self.actor_kind) is not ActorKind or type(self.context_kind) is not ContextKind:
            raise TypeError("Actor y contexto deben proceder del catálogo de auditoría.")
        for code in (self.action_code, self.resource_kind):
            if type(code) is not str or TECHNICAL_CODE.fullmatch(code) is None:
                raise ValueError("La auditoría requiere identificadores técnicos admitidos.")
        require_uuid(self.resource_id)
        for reference in (self.actor_account_id, self.organization_id, self.academic_scope_id):
            require_uuid(reference, optional=True)
        if self.actor_kind is ActorKind.SYSTEM:
            valid_actor = self.actor_account_id is None and self.context_kind is ContextKind.SYSTEM
        else:
            valid_actor = (
                self.actor_account_id is not None and self.context_kind is not ContextKind.SYSTEM
            )
        if not valid_actor or (self.context_kind is ContextKind.ORGANIZATION) != (
            self.organization_id is not None
        ):
            raise ValueError("Actor y contexto de auditoría no son coherentes.")
        if self.reason is not None and type(self.reason) is not AuditReason:
            raise TypeError("El motivo debe proceder del catálogo técnico de auditoría.")
        for projection in (self.before_state, self.after_state):
            if projection is not None:
                if type(projection) is not AuditProjection:
                    raise TypeError("La auditoría solo admite proyecciones explícitas.")
                projection.__post_init__()


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    event_id: UUID
    correlation_id: UUID
    occurred_at: datetime
