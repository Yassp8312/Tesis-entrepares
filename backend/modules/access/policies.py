"""Decisiones puras de M08. Application aporta hechos actuales y el instante.

Una decisión no es un permiso reutilizable ni valida una transición de negocio.
No se consulta persistencia, HTTP, configuración ambiental ni el reloj del sistema.
"""

from datetime import datetime
from types import MappingProxyType

from core.clock import as_utc

from .contracts import (
    AccessDecision,
    AccessFacts,
    Action,
    ActorFacts,
    Condition,
    ContextFacts,
    ContextKind,
    DecisionCode,
    GrantSource,
    ResourceFacts,
    ResourceKind,
    RestrictionContext,
    Scope,
    ScopeKind,
)


def _deny(code=DecisionCode.DEFAULT_DENY):
    return AccessDecision(False, code)


_ALLOW = AccessDecision(True, DecisionCode.ALLOWED)


def _conditions(facts, *required):
    missing = tuple(item for item in required if item not in facts.configured_conditions)
    return AccessDecision(False, DecisionCode.CONDITION_REQUIRED, missing) if missing else _ALLOW


def _authenticated(actor):
    if actor.account_id is None:
        return _deny(DecisionCode.AUTHENTICATION_REQUIRED)
    if not actor.is_active:
        return _deny(DecisionCode.ACCOUNT_INACTIVE)
    return _ALLOW


def _unique(items, key):
    result = {key(item): item for item in items}
    return result if len(result) == len(items) else None


def _lineage(reference, scopes):
    """Devuelve ancestros solo si la rama completa es acíclica y de una institución."""
    result = set()
    institution = None
    while reference is not None:
        if reference in result or reference not in scopes:
            return None
        node = scopes[reference]
        if institution is not None and institution != node.institution_id:
            return None
        institution = node.institution_id
        result.add(reference)
        reference = node.parent_id
    return result


def scope_covers(*, granted: Scope, target: Scope, facts: AccessFacts) -> bool:
    """Inclusión de ámbitos, con grafo académico cerrado aportado por el propietario."""
    if type(granted) is not Scope or type(target) is not Scope or type(facts) is not AccessFacts:
        return False
    scopes = _unique(facts.academic_scopes, lambda item: item.id)
    if scopes is None:
        return False
    # Incluso una concesión global no convierte una referencia académica rota en válida.
    target_lineage = None
    if target.kind is ScopeKind.ACADEMIC:
        target_lineage = _lineage(target.reference_id, scopes)
        if target_lineage is None:
            return False
    if granted.kind is ScopeKind.GLOBAL:
        return True
    if granted.kind is not target.kind:
        return False
    if granted.kind is ScopeKind.ORGANIZATION:
        return granted.reference_id == target.reference_id
    granted_lineage = _lineage(granted.reference_id, scopes)
    return granted_lineage is not None and granted.reference_id in target_lineage


def _live(grant, now):
    return (
        grant.ended_at is None
        and grant.valid_from <= now
        and (grant.valid_until is None or now < grant.valid_until)
    )


def _valid_chain(grant, *, grants, capability, facts, now):
    visited = set()
    while True:
        if grant.id in visited or not _live(grant, now):
            return False
        visited.add(grant.id)
        if not scope_covers(granted=grant.scope, target=grant.scope, facts=facts):
            return False
        if grant.parent_grant_id is None:
            return grant.id in facts.trusted_root_ids and grant.source in (
                GrantSource.BOOTSTRAP,
                GrantSource.ADMINISTRATIVE,
            )
        parent = grants.get(grant.parent_grant_id)
        if (
            parent is None
            or not capability.is_delegable
            or grant.source is not GrantSource.DELEGATION
            or parent.account_id != grant.granted_by
            or parent.capability_code != grant.capability_code
            or not scope_covers(granted=parent.scope, target=grant.scope, facts=facts)
            or grant.valid_from < parent.valid_from
            or (
                parent.valid_until is not None
                and (grant.valid_until is None or grant.valid_until > parent.valid_until)
            )
        ):
            return False
        grant = parent


def check_capability(
    *, actor: ActorFacts, capability_code: str, scope: Scope, facts: AccessFacts, now: datetime
) -> AccessDecision:
    """Posesión vigente, incluida toda cadena de delegación y una raíz confiada explícita.

    No crea concesiones ni decide cómo se reconoce una autoridad inicial (PB03).
    Los IDs confiados se resuelven en el servidor, nunca desde una petición.
    """
    now = as_utc(now)
    if type(actor) is not ActorFacts or type(facts) is not AccessFacts or type(scope) is not Scope:
        return _deny(DecisionCode.INVALID_FACTS)
    authentication = _authenticated(actor)
    if not authentication:
        return authentication
    capabilities = _unique(facts.capabilities, lambda item: item.code)
    grants = _unique(facts.grants, lambda item: item.id)
    if capabilities is None or grants is None:
        return _deny(DecisionCode.INVALID_FACTS)
    capability = capabilities.get(capability_code) if type(capability_code) is str else None
    if capability is not None:
        for grant in facts.grants:
            if (
                grant.account_id == actor.account_id
                and grant.capability_code == capability_code
                and scope_covers(granted=grant.scope, target=scope, facts=facts)
                and _valid_chain(grant, grants=grants, capability=capability, facts=facts, now=now)
            ):
                return _ALLOW
    return _deny(DecisionCode.CAPABILITY_REQUIRED)


def _representation(actor, context, facts, now):
    if context.kind is not ContextKind.ORGANIZATION:
        return _deny(DecisionCode.WRONG_CONTEXT)
    matches = [
        item
        for item in facts.representations
        if item.account_id == actor.account_id
        and item.organization_id == context.organization_id
        and item.created_at <= now
        and item.revoked_at is None
    ]
    if len(matches) != 1:
        return _deny(DecisionCode.REPRESENTATION_REQUIRED)
    representation = matches[0]
    return (
        _ALLOW
        if representation.organization_verified
        else _deny(DecisionCode.REPRESENTATION_REQUIRED)
    )


def _directory(actor, context, facts, now):
    if context.kind is ContextKind.PERSONAL:
        return (
            _ALLOW
            if actor.personal_verified
            else _deny(DecisionCode.PERSONAL_VERIFICATION_REQUIRED)
        )
    return _representation(actor, context, facts, now)


def _owner(actor, context, resource, facts, now):
    if context.kind is ContextKind.PERSONAL:
        if not actor.personal_verified:
            return _deny(DecisionCode.PERSONAL_VERIFICATION_REQUIRED)
        return (
            _ALLOW
            if resource.owner_account_id == actor.account_id
            else _deny(DecisionCode.NOT_OWNER)
        )
    representation = _representation(actor, context, facts, now)
    if not representation:
        return representation
    return (
        _ALLOW
        if resource.owner_organization_id == context.organization_id
        else _deny(DecisionCode.NOT_OWNER)
    )


def _restriction(actor, context, action, facts, now):
    for item in facts.restrictions:
        if (
            item.account_id != actor.account_id
            or item.capability_code != action.value
            or not item.is_ban
            or item.revoked_at is not None
            or now < item.starts_at
            or (item.ends_at is not None and now >= item.ends_at)
        ):
            continue
        matches = (
            item.context is RestrictionContext.BOTH or item.context.value == context.kind.value
        )
        if matches:
            condition = _conditions(facts, Condition.BAN_SCOPE)
            return _deny(DecisionCode.RESTRICTED) if condition else condition
    return _ALLOW


_PUBLIC = MappingProxyType(
    {
        Action.OPPORTUNITY_PUBLIC_READ: ResourceKind.OPPORTUNITY,
        Action.PUBLICATION_PUBLIC_READ: ResourceKind.PUBLICATION,
        Action.ORGANIZATION_PUBLIC_READ: ResourceKind.ORGANIZATION,
    }
)
_CONTENT = MappingProxyType(
    {
        Action.OPPORTUNITY_PUBLISH: (ResourceKind.OPPORTUNITY, (Condition.OPPORTUNITY_CALENDAR,)),
        Action.OPPORTUNITY_MANAGE_READ: (ResourceKind.OPPORTUNITY, ()),
        Action.OPPORTUNITY_UPDATE: (ResourceKind.OPPORTUNITY, ()),
        Action.OPPORTUNITY_CLOSE: (ResourceKind.OPPORTUNITY, ()),
        Action.OPPORTUNITY_EXTEND: (ResourceKind.OPPORTUNITY, (Condition.OPPORTUNITY_CALENDAR,)),
        Action.OPPORTUNITY_REACTIVATE: (
            ResourceKind.OPPORTUNITY,
            (Condition.OPPORTUNITY_CALENDAR,),
        ),
        Action.PUBLICATION_PUBLISH: (ResourceKind.PUBLICATION, ()),
        Action.PUBLICATION_MANAGE_READ: (ResourceKind.PUBLICATION, ()),
        Action.PUBLICATION_MUTATE: (ResourceKind.PUBLICATION, (Condition.PUBLICATION_MUTATION,)),
    }
)
_GLOBAL = frozenset({ScopeKind.GLOBAL})
_ACADEMIC = frozenset({ScopeKind.ACADEMIC})
_GOVERNMENT = MappingProxyType(
    {
        Action.ACADEMIC_SCOPE_MANAGE: (
            ResourceKind.ACADEMIC_SCOPE,
            "academics.scope.manage",
            _ACADEMIC,
            (Condition.ACADEMIC_GOVERNANCE,),
        ),
        Action.PERSONAL_VERIFICATION_REVIEW: (
            ResourceKind.PERSONAL_VERIFICATION,
            "academics.verification.review",
            _ACADEMIC,
            (),
        ),
        Action.RESEARCHER_REQUEST: (
            ResourceKind.RESEARCHER_REQUEST,
            "academics.researcher.request",
            _ACADEMIC,
            (Condition.RESEARCHER_PROTOCOL,),
        ),
        Action.RESEARCHER_AWARD: (
            ResourceKind.RESEARCHER_REQUEST,
            "academics.researcher.award",
            _ACADEMIC,
            (Condition.RESEARCHER_PROTOCOL,),
        ),
        Action.ORGANIZATION_VERIFICATION_REVIEW: (
            ResourceKind.ORGANIZATION_VERIFICATION,
            "organizations.verification.review",
            _GLOBAL,
            (),
        ),
        Action.HIGHLIGHT_CREATE: (
            None,
            "publications.highlight",
            _GLOBAL,
            (Condition.HIGHLIGHT_RULES,),
        ),
        Action.MODERATION_REVIEW: (None, "moderation.review", _GLOBAL, ()),
        Action.BAN_APPLY: (
            ResourceKind.REPORT,
            "moderation.review",
            _GLOBAL,
            (Condition.BAN_SCOPE, Condition.BAN_REVIEW_READY),
        ),
        Action.DOMAIN_MANAGE: (
            ResourceKind.DOMAIN,
            "academics.domain.manage",
            _GLOBAL,
            (Condition.DOMAIN_GOVERNANCE,),
        ),
        Action.RECOVERY_REVIEW: (
            ResourceKind.RECOVERY_REQUEST,
            "identity.recovery.review",
            _GLOBAL,
            (Condition.RECOVERY_PROTOCOL,),
        ),
        Action.AUDIT_READ: (ResourceKind.AUDIT_EVENT, "audit.read", frozenset(ScopeKind), ()),
    }
)


def _public(action, context, resource, now):
    if context.kind is not ContextKind.PUBLIC:
        return _deny(DecisionCode.WRONG_CONTEXT)
    if resource.kind is not _PUBLIC[action]:
        return _deny()
    visible = (
        resource.visibility == "visible"
        and resource.published_at is not None
        and resource.published_at <= now
    )
    if action is Action.OPPORTUNITY_PUBLIC_READ:
        visible = (
            visible
            and resource.status == "active"
            and resource.expires_at is not None
            and now < resource.expires_at
        )
    elif action is Action.PUBLICATION_PUBLIC_READ:
        visible = visible and resource.status == "published"
    else:
        visible = visible and resource.organization_verified and resource.status == "published"
    return _ALLOW if visible else _deny(DecisionCode.NOT_PUBLIC)


def _government(action, actor, context, resource, facts, now):
    if context.kind is not ContextKind.PERSONAL:
        return _deny(DecisionCode.WRONG_CONTEXT)
    kind, capability, scopes, conditions = _GOVERNMENT[action]
    if kind is not None and resource.kind is not kind:
        return _deny()
    if resource.scope.kind not in scopes:
        return _deny()
    if action is Action.HIGHLIGHT_CREATE and resource.kind not in (
        ResourceKind.OPPORTUNITY,
        ResourceKind.PUBLICATION,
    ):
        return _deny()
    if action is Action.MODERATION_REVIEW and resource.kind not in (
        ResourceKind.REPORT,
        ResourceKind.REVIEW_REQUEST,
    ):
        return _deny()
    possession = check_capability(
        actor=actor, capability_code=capability, scope=resource.scope, facts=facts, now=now
    )
    if not possession:
        return possession
    if action is Action.AUDIT_READ and resource.audit_type not in facts.allowed_audit_types:
        return _deny(DecisionCode.AUDIT_TYPE_DENIED)
    return _conditions(facts, *conditions)


def authorize(
    *,
    action: Action | str,
    actor: ActorFacts,
    context: ContextFacts,
    resource: ResourceFacts,
    facts: AccessFacts,
    now: datetime,
) -> AccessDecision:
    """Autoriza una acción interna conocida por actor, contexto y recurso exactos.

    Application reconstruirá estos hechos desde los selectores propietarios en cada
    caso; deberá validar además estados, transiciones, contenido y concurrencia.
    """
    now = as_utc(now)
    if (
        type(actor) is not ActorFacts
        or type(context) is not ContextFacts
        or type(resource) is not ResourceFacts
        or type(facts) is not AccessFacts
    ):
        return _deny(DecisionCode.INVALID_FACTS)
    if type(action) not in (Action, str):
        return _deny()
    try:
        action = Action(action)
    except ValueError:
        return _deny()
    if action in _PUBLIC:
        return _public(action, context, resource, now)
    authentication = _authenticated(actor)
    if not authentication:
        return authentication
    if context.kind is ContextKind.PUBLIC:
        return _deny(DecisionCode.WRONG_CONTEXT)
    # Derecho propio: ni una restricción ni una condición ajena cierran esta vía.
    if action in (Action.MEASURE_SELF_READ, Action.MEASURE_REVIEW_REQUEST):
        if context.kind is not ContextKind.PERSONAL or resource.kind is not ResourceKind.MEASURE:
            return _deny()
        return (
            _ALLOW
            if resource.affected_account_id == actor.account_id
            else _deny(DecisionCode.NOT_OWNER)
        )
    restriction = _restriction(actor, context, action, facts, now)
    if not restriction:
        return restriction
    if action in (Action.CONFIRMATION_SAMPLE_PREPARE, Action.CONFIRMATION_SAMPLE_CANCEL):
        if context.kind is not ContextKind.PERSONAL or resource.kind is not ResourceKind.ACCOUNT:
            return _deny()
        return (
            _ALLOW
            if resource.id == resource.owner_account_id == actor.account_id
            else _deny(DecisionCode.NOT_OWNER)
        )
    if action in (Action.DIRECTORY_READ, Action.DIRECTORY_RESEARCHER_FILTER):
        if resource.kind is not ResourceKind.DIRECTORY:
            return _deny()
        directory = _directory(actor, context, facts, now)
        if not directory:
            return directory
        return (
            _conditions(facts, Condition.RESEARCHER_FILTER)
            if action is Action.DIRECTORY_RESEARCHER_FILTER
            else _ALLOW
        )
    if action in (Action.PROFILE_READ, Action.PROFILE_CONTACT_READ, Action.PROFILE_SELF_MANAGE):
        if resource.kind is not ResourceKind.PROFILE:
            return _deny()
        if context.kind is ContextKind.PERSONAL and resource.owner_account_id == actor.account_id:
            return _ALLOW
        if action is Action.PROFILE_SELF_MANAGE:
            return _deny(DecisionCode.NOT_OWNER)
        directory = _directory(actor, context, facts, now)
        if not directory:
            return directory
        if not resource.profile_complete:
            return _deny(DecisionCode.RESOURCE_INCOMPLETE)
        if action is Action.PROFILE_CONTACT_READ and not resource.contact_visible:
            return _deny(DecisionCode.PRIVATE_CONTACT)
        return _ALLOW
    if action in _CONTENT:
        kind, conditions = _CONTENT[action]
        if resource.kind is not kind:
            return _deny()
        ownership = _owner(actor, context, resource, facts, now)
        return _conditions(facts, *conditions) if ownership else ownership
    if action is Action.ORGANIZATION_MANAGE:
        if resource.kind is not ResourceKind.ORGANIZATION:
            return _deny()
        representation = _representation(actor, context, facts, now)
        if not representation:
            return representation
        return _ALLOW if resource.id == context.organization_id else _deny(DecisionCode.NOT_OWNER)
    if action is Action.REPORT_CREATE:
        if context.kind is not ContextKind.PERSONAL:
            return _deny(DecisionCode.WRONG_CONTEXT)
        if resource.kind not in (
            ResourceKind.OPPORTUNITY,
            ResourceKind.PUBLICATION,
            ResourceKind.PROFILE,
        ):
            return _deny()
        return (
            _ALLOW
            if actor.personal_verified
            else _deny(DecisionCode.PERSONAL_VERIFICATION_REQUIRED)
        )
    if action in _GOVERNMENT:
        return _government(action, actor, context, resource, facts, now)
    return _deny()
