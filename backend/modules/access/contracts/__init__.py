"""Tipos de intercambio de M08; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from core.clock import as_utc


class ContextKind(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    ORGANIZATION = "organization"


class ScopeKind(StrEnum):
    GLOBAL = "global"
    ACADEMIC = "academic"
    ORGANIZATION = "organization"


class GrantSource(StrEnum):
    BOOTSTRAP = "bootstrap"
    ADMINISTRATIVE = "administrative"
    DELEGATION = "delegation"


class RestrictionContext(StrEnum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"
    BOTH = "both"


class Condition(StrEnum):
    OPPORTUNITY_CALENDAR = "Q03_Q08_opportunity_calendar"
    PUBLICATION_MUTATION = "RF45_publication_mutation"
    RESEARCHER_FILTER = "RF59_researcher_filter"
    ACADEMIC_GOVERNANCE = "PB03_academic_governance"
    RESEARCHER_PROTOCOL = "Q05_researcher_protocol"
    DOMAIN_GOVERNANCE = "PB03_domain_governance"
    HIGHLIGHT_RULES = "PB06_Q11_highlight_rules"
    RECOVERY_PROTOCOL = "PB02_Q13_recovery_protocol"
    BAN_SCOPE = "PB01_Q07_ban_scope"
    BAN_REVIEW_READY = "PB01_Q07_ban_review_ready"


class ResourceKind(StrEnum):
    ACCOUNT = "account"
    DIRECTORY = "directory"
    PROFILE = "profile"
    OPPORTUNITY = "opportunity"
    PUBLICATION = "publication"
    ORGANIZATION = "organization"
    MEASURE = "measure"
    ACADEMIC_SCOPE = "academic_scope"
    PERSONAL_VERIFICATION = "personal_verification"
    RESEARCHER_REQUEST = "researcher_request"
    ORGANIZATION_VERIFICATION = "organization_verification"
    DOMAIN = "domain"
    REPORT = "report"
    REVIEW_REQUEST = "review_request"
    RECOVERY_REQUEST = "recovery_request"
    AUDIT_EVENT = "audit_event"


class Action(StrEnum):
    """Identificadores internos del servidor; no son una lista de endpoints habilitados."""

    OPPORTUNITY_PUBLIC_READ = "opportunities.public_read"
    CONFIRMATION_SAMPLE_PREPARE = "identity.confirmation_sample.prepare"
    CONFIRMATION_SAMPLE_CANCEL = "identity.confirmation_sample.cancel"
    PUBLICATION_PUBLIC_READ = "publications.public_read"
    ORGANIZATION_PUBLIC_READ = "organizations.public_read"
    DIRECTORY_READ = "directory.read"
    PROFILE_READ = "profiles.read"
    PROFILE_CONTACT_READ = "profiles.contact.read"
    PROFILE_SELF_MANAGE = "profiles.self.manage"
    DIRECTORY_RESEARCHER_FILTER = "directory.researcher_filter"
    OPPORTUNITY_PUBLISH = "opportunities.publish"
    OPPORTUNITY_MANAGE_READ = "opportunities.manage.read"
    OPPORTUNITY_UPDATE = "opportunities.update"
    OPPORTUNITY_CLOSE = "opportunities.close"
    OPPORTUNITY_EXTEND = "opportunities.extend"
    OPPORTUNITY_REACTIVATE = "opportunities.reactivate"
    PUBLICATION_PUBLISH = "publications.publish"
    PUBLICATION_MANAGE_READ = "publications.manage.read"
    PUBLICATION_MUTATE = "publications.mutate"
    ORGANIZATION_MANAGE = "organizations.manage"
    REPORT_CREATE = "moderation.report"
    MEASURE_SELF_READ = "moderation.measure.self.read"
    MEASURE_REVIEW_REQUEST = "moderation.request_review"
    ACADEMIC_SCOPE_MANAGE = "academics.scope.manage"
    PERSONAL_VERIFICATION_REVIEW = "academics.verification.review"
    RESEARCHER_REQUEST = "academics.researcher.request"
    RESEARCHER_AWARD = "academics.researcher.award"
    ORGANIZATION_VERIFICATION_REVIEW = "organizations.verification.review"
    HIGHLIGHT_CREATE = "publications.highlight"
    MODERATION_REVIEW = "moderation.review"
    BAN_APPLY = "moderation.ban.apply"
    DOMAIN_MANAGE = "academics.domain.manage"
    RECOVERY_REVIEW = "identity.recovery.review"
    AUDIT_READ = "audit.read"


class DecisionCode(StrEnum):
    ALLOWED = "allowed"
    DEFAULT_DENY = "default_deny"
    INVALID_FACTS = "invalid_facts"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ACCOUNT_INACTIVE = "account_inactive"
    WRONG_CONTEXT = "wrong_context"
    REPRESENTATION_REQUIRED = "representation_required"
    PERSONAL_VERIFICATION_REQUIRED = "personal_verification_required"
    NOT_OWNER = "not_owner"
    RESOURCE_INCOMPLETE = "resource_incomplete"
    PRIVATE_CONTACT = "private_contact"
    NOT_PUBLIC = "not_public"
    CAPABILITY_REQUIRED = "capability_required"
    CONDITION_REQUIRED = "condition_required"
    RESTRICTED = "restricted"
    AUDIT_TYPE_DENIED = "audit_type_denied"


def _uuid(value, *, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, UUID):
        raise TypeError("Se requiere una referencia UUID interna.")


def _booleans(*values):
    if any(type(value) is not bool for value in values):
        raise TypeError("Los hechos booleanos deben ser explícitos.")


def _code(value):
    if type(value) is not str or not value.strip() or len(value) > 80:
        raise ValueError("Se requiere un código técnico de capacidad.")


def _dates(instance, *names):
    for name in names:
        value = getattr(instance, name)
        if value is not None:
            object.__setattr__(instance, name, as_utc(value))


@dataclass(frozen=True, slots=True)
class ActorFacts:
    account_id: UUID | None = None
    is_active: bool = False
    personal_verified: bool = False
    is_staff: bool = False
    is_superuser: bool = False

    def __post_init__(self):
        _uuid(self.account_id, optional=True)
        _booleans(self.is_active, self.personal_verified, self.is_staff, self.is_superuser)


@dataclass(frozen=True, slots=True)
class ContextFacts:
    kind: ContextKind
    organization_id: UUID | None = None

    def __post_init__(self):
        if type(self.kind) is not ContextKind:
            raise TypeError("Se requiere un contexto explícito.")
        _uuid(self.organization_id, optional=True)
        if (self.kind is ContextKind.ORGANIZATION) != (self.organization_id is not None):
            raise ValueError(
                "El contexto organizacional requiere su entidad y solo esa clase la admite."
            )


@dataclass(frozen=True, slots=True)
class Scope:
    kind: ScopeKind = ScopeKind.GLOBAL
    reference_id: UUID | None = None

    def __post_init__(self):
        if type(self.kind) is not ScopeKind:
            raise TypeError("Se requiere un ámbito explícito.")
        _uuid(self.reference_id, optional=True)
        if (self.kind is ScopeKind.GLOBAL) != (self.reference_id is None):
            raise ValueError("Las referencias de ámbito no son coherentes.")


@dataclass(frozen=True, slots=True)
class AcademicScopeFacts:
    id: UUID
    institution_id: UUID
    parent_id: UUID | None = None

    def __post_init__(self):
        _uuid(self.id)
        _uuid(self.institution_id)
        _uuid(self.parent_id, optional=True)


@dataclass(frozen=True, slots=True)
class CapabilityFacts:
    code: str
    is_delegable: bool = False

    def __post_init__(self):
        _code(self.code)
        _booleans(self.is_delegable)


@dataclass(frozen=True, slots=True)
class GrantFacts:
    id: UUID
    account_id: UUID
    capability_code: str
    scope: Scope
    granted_by: UUID
    source: GrantSource
    valid_from: datetime
    valid_until: datetime | None = None
    ended_at: datetime | None = None
    parent_grant_id: UUID | None = None

    def __post_init__(self):
        for value in (self.id, self.account_id, self.granted_by):
            _uuid(value)
        _uuid(self.parent_grant_id, optional=True)
        _code(self.capability_code)
        if type(self.scope) is not Scope or type(self.source) is not GrantSource:
            raise TypeError("La concesión requiere ámbito y procedencia internos.")
        if self.valid_from is None:
            raise TypeError("La concesión requiere inicio de vigencia.")
        _dates(self, "valid_from", "valid_until", "ended_at")


@dataclass(frozen=True, slots=True)
class RepresentationFacts:
    account_id: UUID
    organization_id: UUID
    organization_verified: bool
    created_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self):
        _uuid(self.account_id)
        _uuid(self.organization_id)
        _booleans(self.organization_verified)
        if self.created_at is None:
            raise TypeError("La representación requiere fecha de inicio.")
        _dates(self, "created_at", "revoked_at")


@dataclass(frozen=True, slots=True)
class RestrictionFacts:
    account_id: UUID
    capability_code: str
    context: RestrictionContext
    starts_at: datetime
    ends_at: datetime | None = None
    revoked_at: datetime | None = None
    is_ban: bool = True

    def __post_init__(self):
        _uuid(self.account_id)
        _code(self.capability_code)
        if type(self.context) is not RestrictionContext:
            raise TypeError("La restricción requiere un contexto explícito.")
        _booleans(self.is_ban)
        if self.starts_at is None:
            raise TypeError("La restricción requiere inicio de vigencia.")
        _dates(self, "starts_at", "ends_at", "revoked_at")


@dataclass(frozen=True, slots=True)
class ResourceFacts:
    kind: ResourceKind
    id: UUID | None = None
    owner_account_id: UUID | None = None
    owner_organization_id: UUID | None = None
    affected_account_id: UUID | None = None
    scope: Scope = Scope()
    profile_complete: bool = False
    contact_visible: bool = False
    organization_verified: bool = False
    status: str | None = None
    visibility: str | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    audit_type: str | None = None

    def __post_init__(self):
        if type(self.kind) is not ResourceKind or type(self.scope) is not Scope:
            raise TypeError("Se requiere un recurso y ámbito explícitos.")
        for reference in (
            self.id,
            self.owner_account_id,
            self.owner_organization_id,
            self.affected_account_id,
        ):
            _uuid(reference, optional=True)
        _booleans(self.profile_complete, self.contact_visible, self.organization_verified)
        if self.owner_account_id is not None and self.owner_organization_id is not None:
            raise ValueError("La titularidad debe ser excluyente.")
        for value in (self.status, self.visibility, self.audit_type):
            if value is not None and type(value) is not str:
                raise TypeError("Los estados del recurso deben ser códigos internos.")
        _dates(self, "published_at", "expires_at")


@dataclass(frozen=True, slots=True)
class AccessFacts:
    capabilities: tuple[CapabilityFacts, ...] = ()
    grants: tuple[GrantFacts, ...] = ()
    academic_scopes: tuple[AcademicScopeFacts, ...] = ()
    representations: tuple[RepresentationFacts, ...] = ()
    restrictions: tuple[RestrictionFacts, ...] = ()
    trusted_root_ids: frozenset[UUID] = frozenset()
    configured_conditions: frozenset[Condition] = frozenset()
    allowed_audit_types: frozenset[str] = frozenset()

    def __post_init__(self):
        for values, kind in (
            (self.capabilities, CapabilityFacts),
            (self.grants, GrantFacts),
            (self.academic_scopes, AcademicScopeFacts),
            (self.representations, RepresentationFacts),
            (self.restrictions, RestrictionFacts),
        ):
            if type(values) is not tuple or any(type(value) is not kind for value in values):
                raise TypeError("Se requieren hechos tipados en tuplas inmutables.")
        if type(self.trusted_root_ids) is not frozenset or any(
            not isinstance(v, UUID) for v in self.trusted_root_ids
        ):
            raise TypeError("Las raíces de confianza deben proceder de configuración del servidor.")
        if type(self.configured_conditions) is not frozenset or any(
            type(v) is not Condition for v in self.configured_conditions
        ):
            raise TypeError("Las condiciones requieren configuración explícita.")
        if type(self.allowed_audit_types) is not frozenset or any(
            type(v) is not str or not v.strip() for v in self.allowed_audit_types
        ):
            raise TypeError("La lectura de auditoría requiere tipos permitidos explícitos.")


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    code: DecisionCode
    required_conditions: tuple[Condition, ...] = ()

    def __post_init__(self):
        _booleans(self.allowed)
        if type(self.code) is not DecisionCode:
            raise TypeError("Se requiere un resultado de decisión explícito.")
        if self.allowed != (self.code is DecisionCode.ALLOWED):
            raise ValueError("El resultado y su código deben coincidir.")
        if type(self.required_conditions) is not tuple or any(
            type(value) is not Condition for value in self.required_conditions
        ):
            raise TypeError("Las condiciones pendientes deben ser inmutables y explícitas.")
        if bool(self.required_conditions) != (self.code is DecisionCode.CONDITION_REQUIRED):
            raise ValueError(
                "Solo una denegación condicional debe enumerar condiciones pendientes."
            )

    def __bool__(self):
        return self.allowed
