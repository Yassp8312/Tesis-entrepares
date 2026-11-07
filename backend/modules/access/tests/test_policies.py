"""Matriz sintética de autorización; pytest-django prohíbe acceso a BD en estos casos."""

import ast
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from modules.access.contracts import (
    AcademicScopeFacts,
    AccessDecision,
    AccessFacts,
    Action,
    ActorFacts,
    CapabilityFacts,
    Condition,
    ContextFacts,
    ContextKind,
    DecisionCode,
    GrantFacts,
    GrantSource,
    RepresentationFacts,
    ResourceFacts,
    ResourceKind,
    RestrictionContext,
    RestrictionFacts,
    Scope,
    ScopeKind,
)
from modules.access.policies import authorize, check_capability, scope_covers

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
DAY = timedelta(days=1)
USER, OTHER, ORG, OTHER_ORG = (UUID(int=i) for i in (1, 2, 3, 4))
UNIVERSITY, FACULTY, CAREER, SIBLING, OUTSIDE = (UUID(int=i) for i in (20, 21, 22, 23, 30))
ROOT_ID, CHILD_ID = UUID(int=100), UUID(int=101)
PERSONAL = ContextFacts(ContextKind.PERSONAL)
ORGANIZATIONAL = ContextFacts(ContextKind.ORGANIZATION, ORG)
PUBLIC = ContextFacts(ContextKind.PUBLIC)
ACTOR = ActorFacts(USER, is_active=True, personal_verified=True)
ACADEMIC_SCOPES = (
    AcademicScopeFacts(UNIVERSITY, UNIVERSITY),
    AcademicScopeFacts(FACULTY, UNIVERSITY, UNIVERSITY),
    AcademicScopeFacts(CAREER, UNIVERSITY, FACULTY),
    AcademicScopeFacts(SIBLING, UNIVERSITY, UNIVERSITY),
    AcademicScopeFacts(OUTSIDE, OUTSIDE),
)
REPRESENTATION = RepresentationFacts(USER, ORG, True, NOW - DAY)
ALL_CONFIGURED = frozenset(Condition)


def decide(action=Action.DIRECTORY_READ, **changes):
    parameters = {
        "action": action,
        "actor": ACTOR,
        "context": PERSONAL,
        "resource": ResourceFacts(ResourceKind.DIRECTORY),
        "facts": AccessFacts(),
        "now": NOW,
    }
    parameters.update(changes)
    return authorize(**parameters)


def backing(code="academics.verification.review", **changes):
    root = GrantFacts(
        ROOT_ID,
        OTHER,
        code,
        Scope(ScopeKind.ACADEMIC, UNIVERSITY),
        UUID(int=99),
        GrantSource.BOOTSTRAP,
        NOW - 30 * DAY,
        NOW + 10 * DAY,
    )
    child = GrantFacts(
        CHILD_ID,
        USER,
        code,
        Scope(ScopeKind.ACADEMIC, FACULTY),
        OTHER,
        GrantSource.DELEGATION,
        NOW - 10 * DAY,
        NOW + 3 * DAY,
        parent_grant_id=ROOT_ID,
    )
    parameters = {
        "capabilities": (CapabilityFacts(code, is_delegable=True),),
        "grants": (root, child),
        "academic_scopes": ACADEMIC_SCOPES,
        "trusted_root_ids": frozenset({ROOT_ID}),
    }
    parameters.update(changes)
    return AccessFacts(**parameters)


def capability(facts=None, **changes):
    parameters = {
        "actor": ACTOR,
        "capability_code": "academics.verification.review",
        "scope": Scope(ScopeKind.ACADEMIC, CAREER),
        "facts": backing() if facts is None else facts,
        "now": NOW,
    }
    parameters.update(changes)
    return check_capability(**parameters)


@pytest.mark.parametrize("action", list(Action) + ["unknown", "*", "", "audit.*", None, 1, {}])
def test_guest_and_unknown_actions_never_gain_private_access(action):
    result = decide(action, actor=ActorFacts())
    assert result.allowed is False
    assert not result


@pytest.mark.parametrize("action", [a for a in Action if "public_read" not in a.value])
def test_inactive_account_cannot_use_private_actions(action):
    assert (
        decide(action, actor=replace(ACTOR, is_active=False)).code is DecisionCode.ACCOUNT_INACTIVE
    )


@pytest.mark.parametrize(
    "flags", [{"is_staff": True}, {"is_superuser": True}, {"is_staff": True, "is_superuser": True}]
)
@pytest.mark.parametrize(
    "action,kind",
    [
        (Action.ACADEMIC_SCOPE_MANAGE, ResourceKind.ACADEMIC_SCOPE),
        (Action.PERSONAL_VERIFICATION_REVIEW, ResourceKind.PERSONAL_VERIFICATION),
        (Action.RESEARCHER_AWARD, ResourceKind.RESEARCHER_REQUEST),
        (Action.ORGANIZATION_VERIFICATION_REVIEW, ResourceKind.ORGANIZATION_VERIFICATION),
        (Action.HIGHLIGHT_CREATE, ResourceKind.PUBLICATION),
        (Action.MODERATION_REVIEW, ResourceKind.REPORT),
        (Action.DOMAIN_MANAGE, ResourceKind.DOMAIN),
        (Action.RECOVERY_REVIEW, ResourceKind.RECOVERY_REQUEST),
        (Action.AUDIT_READ, ResourceKind.AUDIT_EVENT),
    ],
)
def test_technical_privileges_are_not_product_authority(flags, action, kind):
    resource = ResourceFacts(
        kind,
        scope=Scope(ScopeKind.ACADEMIC, CAREER)
        if "academics." in action.value and action is not Action.DOMAIN_MANAGE
        else Scope(),
    )
    assert not decide(action, actor=replace(ACTOR, **flags), resource=resource)


@pytest.mark.parametrize(
    "field,value", [("actor", {}), ("context", "personal"), ("resource", None), ("facts", {})]
)
def test_untyped_inputs_fail_closed(field, value):
    assert decide(**{field: value}).code is DecisionCode.INVALID_FACTS


@pytest.mark.parametrize("instant", [datetime(2026, 1, 1), "2026-11-07", None])
def test_time_must_be_explicit_and_aware(instant):
    with pytest.raises((TypeError, ValueError)):
        decide(now=instant)


@pytest.mark.parametrize(
    "kind,action,status",
    [
        (ResourceKind.OPPORTUNITY, Action.OPPORTUNITY_PUBLIC_READ, "active"),
        (ResourceKind.PUBLICATION, Action.PUBLICATION_PUBLIC_READ, "published"),
        (ResourceKind.ORGANIZATION, Action.ORGANIZATION_PUBLIC_READ, "published"),
    ],
)
def test_published_visible_public_resources_are_readable_without_session(kind, action, status):
    resource = ResourceFacts(
        kind,
        status=status,
        visibility="visible",
        published_at=NOW,
        expires_at=NOW + DAY,
        organization_verified=True,
    )
    assert decide(action, actor=ActorFacts(), context=PUBLIC, resource=resource)
    assert decide(action, actor=replace(ACTOR, is_active=False), context=PUBLIC, resource=resource)
    assert not decide(action, resource=resource)  # Contexto público explícito.
    assert not decide(action, context=PUBLIC, resource=replace(resource, kind=ResourceKind.MEASURE))
    for change in (
        {"visibility": "hidden"},
        {"published_at": None},
        {"published_at": NOW + DAY},
        {"status": "draft"},
    ):
        assert not decide(action, context=PUBLIC, resource=replace(resource, **change))


@pytest.mark.parametrize(
    "change",
    [
        {"expires_at": NOW},
        {"expires_at": NOW - DAY},
        {"expires_at": None},
        {"status": "closed"},
        {"status": "expired"},
    ],
)
def test_opportunity_expiry_and_archive_are_not_inferred(change):
    resource = ResourceFacts(
        ResourceKind.OPPORTUNITY,
        status="active",
        visibility="visible",
        published_at=NOW - DAY,
        expires_at=NOW + DAY,
    )
    assert not decide(
        Action.OPPORTUNITY_PUBLIC_READ, context=PUBLIC, resource=replace(resource, **change)
    )


def test_public_organization_requires_backing_and_publication():
    resource = ResourceFacts(
        ResourceKind.ORGANIZATION,
        status="published",
        visibility="visible",
        published_at=NOW,
        organization_verified=False,
    )
    assert (
        decide(Action.ORGANIZATION_PUBLIC_READ, context=PUBLIC, resource=resource).code
        is DecisionCode.NOT_PUBLIC
    )


def test_directory_separates_personal_and_organization_backing():
    unverified = replace(ACTOR, personal_verified=False)
    facts = AccessFacts(representations=(REPRESENTATION,))
    assert decide()
    assert not decide(actor=unverified, facts=facts)  # Representar no verifica a la persona.
    assert decide(actor=unverified, context=ORGANIZATIONAL, facts=facts)
    assert not decide(context=ORGANIZATIONAL)  # Verificación personal no representa entidad.
    assert not decide(actor=ActorFacts(is_superuser=True), context=PUBLIC)


@pytest.mark.parametrize(
    "change",
    [
        {"account_id": OTHER},
        {"organization_id": OTHER_ORG},
        {"organization_verified": False},
        {"revoked_at": NOW},
        {"revoked_at": NOW + DAY},
        {"created_at": NOW + DAY},
    ],
)
def test_representation_must_match_and_remain_current(change):
    facts = AccessFacts(representations=(replace(REPRESENTATION, **change),))
    assert not decide(context=ORGANIZATIONAL, facts=facts)


def test_duplicate_representation_facts_are_not_an_implicit_vote():
    facts = AccessFacts(
        representations=(REPRESENTATION, replace(REPRESENTATION, organization_verified=False))
    )
    assert not decide(context=ORGANIZATIONAL, facts=facts)


def test_reinstated_representative_can_act_without_erasing_revoked_history():
    historical = replace(REPRESENTATION, created_at=NOW - 3 * DAY, revoked_at=NOW - 2 * DAY)
    facts = AccessFacts(representations=(historical, REPRESENTATION))
    assert decide(context=ORGANIZATIONAL, facts=facts)


@pytest.mark.parametrize(
    "action", [Action.PROFILE_READ, Action.PROFILE_CONTACT_READ, Action.PROFILE_SELF_MANAGE]
)
def test_own_profile_remains_manageable_before_verification_and_completion(action):
    resource = ResourceFacts(ResourceKind.PROFILE, owner_account_id=USER)
    assert decide(action, actor=replace(ACTOR, personal_verified=False), resource=resource)
    assert not decide(action, actor=replace(ACTOR, is_active=False), resource=resource)


def test_directory_contains_unverified_but_complete_profiles_and_only_visible_contacts():
    # El recurso no exige respaldo del titular; ese hecho no pertenece al criterio de aparición.
    resource = ResourceFacts(ResourceKind.PROFILE, owner_account_id=OTHER, profile_complete=True)
    assert decide(Action.PROFILE_READ, resource=resource)
    assert not decide(Action.PROFILE_SELF_MANAGE, resource=resource)
    assert (
        decide(Action.PROFILE_CONTACT_READ, resource=resource).code is DecisionCode.PRIVATE_CONTACT
    )
    assert decide(Action.PROFILE_CONTACT_READ, resource=replace(resource, contact_visible=True))
    assert (
        decide(Action.PROFILE_READ, resource=replace(resource, profile_complete=False)).code
        is DecisionCode.RESOURCE_INCOMPLETE
    )
    assert not decide(
        Action.PROFILE_CONTACT_READ,
        actor=replace(ACTOR, is_superuser=True, is_staff=True),
        resource=resource,
    )


def test_org_context_does_not_reveal_own_hidden_contact_as_a_personal_edit():
    resource = ResourceFacts(ResourceKind.PROFILE, owner_account_id=USER, profile_complete=True)
    facts = AccessFacts(representations=(REPRESENTATION,))
    assert (
        decide(
            Action.PROFILE_CONTACT_READ, context=ORGANIZATIONAL, resource=resource, facts=facts
        ).code
        is DecisionCode.PRIVATE_CONTACT
    )


@pytest.mark.parametrize(
    "kind,action",
    [
        (ResourceKind.OPPORTUNITY, Action.OPPORTUNITY_MANAGE_READ),
        (ResourceKind.OPPORTUNITY, Action.OPPORTUNITY_UPDATE),
        (ResourceKind.OPPORTUNITY, Action.OPPORTUNITY_CLOSE),
        (ResourceKind.PUBLICATION, Action.PUBLICATION_PUBLISH),
        (ResourceKind.PUBLICATION, Action.PUBLICATION_MANAGE_READ),
    ],
)
def test_content_ownership_and_context_cannot_be_substituted(kind, action):
    personal = ResourceFacts(kind, owner_account_id=USER)
    organizational = ResourceFacts(kind, owner_organization_id=ORG)
    facts = AccessFacts(representations=(REPRESENTATION,))
    unverified = replace(ACTOR, personal_verified=False)
    assert decide(action, resource=personal)
    assert not decide(action, actor=unverified, resource=personal, facts=facts)
    assert not decide(action, resource=replace(personal, owner_account_id=OTHER))
    assert not decide(action, resource=organizational)
    assert decide(
        action, actor=unverified, context=ORGANIZATIONAL, resource=organizational, facts=facts
    )
    assert not decide(
        action,
        context=ORGANIZATIONAL,
        resource=replace(organizational, owner_organization_id=OTHER_ORG),
        facts=facts,
    )
    assert not decide(action, context=ORGANIZATIONAL, resource=personal, facts=facts)
    revoked = replace(facts, representations=(replace(REPRESENTATION, revoked_at=NOW),))
    assert not decide(action, context=ORGANIZATIONAL, resource=organizational, facts=revoked)
    assert decide(
        action, resource=personal, facts=revoked
    )  # Revocar no borra sus derechos personales.


@pytest.mark.parametrize(
    "action,kind,condition",
    [
        (Action.OPPORTUNITY_PUBLISH, ResourceKind.OPPORTUNITY, Condition.OPPORTUNITY_CALENDAR),
        (Action.OPPORTUNITY_EXTEND, ResourceKind.OPPORTUNITY, Condition.OPPORTUNITY_CALENDAR),
        (Action.OPPORTUNITY_REACTIVATE, ResourceKind.OPPORTUNITY, Condition.OPPORTUNITY_CALENDAR),
        (Action.PUBLICATION_MUTATE, ResourceKind.PUBLICATION, Condition.PUBLICATION_MUTATION),
        (Action.DIRECTORY_RESEARCHER_FILTER, ResourceKind.DIRECTORY, Condition.RESEARCHER_FILTER),
    ],
)
def test_pending_rules_affect_only_their_branches(action, kind, condition):
    resource = ResourceFacts(kind, owner_account_id=USER)
    result = decide(action, resource=resource)
    assert result.code is DecisionCode.CONDITION_REQUIRED
    assert result.required_conditions == (condition,)
    assert decide(
        action, resource=resource, facts=AccessFacts(configured_conditions=frozenset({condition}))
    )
    assert decide()  # Buscar normalmente no depende de RF59 ni del calendario.
    assert decide(
        Action.OPPORTUNITY_CLOSE,
        resource=ResourceFacts(ResourceKind.OPPORTUNITY, owner_account_id=USER),
    )
    assert decide(
        Action.PUBLICATION_PUBLISH,
        resource=ResourceFacts(ResourceKind.PUBLICATION, owner_account_id=USER),
    )


def test_org_management_is_for_the_exact_entity_and_reports_are_personal():
    facts = AccessFacts(representations=(REPRESENTATION,))
    resource = ResourceFacts(ResourceKind.ORGANIZATION, id=ORG)
    assert decide(
        Action.ORGANIZATION_MANAGE, context=ORGANIZATIONAL, resource=resource, facts=facts
    )
    assert not decide(
        Action.ORGANIZATION_MANAGE,
        context=ORGANIZATIONAL,
        resource=replace(resource, id=OTHER_ORG),
        facts=facts,
    )
    target = ResourceFacts(ResourceKind.PUBLICATION)
    assert decide(Action.REPORT_CREATE, resource=target)
    assert not decide(
        Action.REPORT_CREATE, resource=target, actor=replace(ACTOR, personal_verified=False)
    )
    assert not decide(Action.REPORT_CREATE, context=ORGANIZATIONAL, resource=target, facts=facts)


def restriction(action=Action.DIRECTORY_READ, **changes):
    parameters = {
        "account_id": USER,
        "capability_code": action.value,
        "context": RestrictionContext.PERSONAL,
        "starts_at": NOW - DAY,
        "ends_at": NOW + DAY,
    }
    parameters.update(changes)
    return RestrictionFacts(**parameters)


def test_current_restriction_denies_even_before_scope_configuration():
    facts = AccessFacts(restrictions=(restriction(),))
    assert decide(facts=facts).required_conditions == (Condition.BAN_SCOPE,)
    configured = replace(facts, configured_conditions=frozenset({Condition.BAN_SCOPE}))
    assert decide(facts=configured).code is DecisionCode.RESTRICTED
    # Una restricción no relacionada no convierte una condición pendiente en bloqueo global.
    assert decide(
        Action.PROFILE_SELF_MANAGE,
        resource=ResourceFacts(ResourceKind.PROFILE, owner_account_id=USER),
        facts=facts,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"account_id": OTHER},
        {"capability_code": "opportunities.close"},
        {"context": RestrictionContext.ORGANIZATION},
        {"starts_at": NOW + DAY},
        {"ends_at": NOW},
        {"revoked_at": NOW},
        {"is_ban": False},
    ],
)
def test_unrelated_or_ineffective_restriction_does_not_deny(change):
    assert decide(facts=AccessFacts(restrictions=(restriction(**change),)))


@pytest.mark.parametrize("context", [RestrictionContext.ORGANIZATION, RestrictionContext.BOTH])
def test_restriction_uses_selected_context(context):
    facts = AccessFacts(
        representations=(REPRESENTATION,),
        restrictions=(restriction(context=context),),
        configured_conditions=ALL_CONFIGURED,
    )
    assert not decide(context=ORGANIZATIONAL, facts=facts)
    if context is RestrictionContext.ORGANIZATION:
        assert decide(facts=facts)


@pytest.mark.parametrize("action", [Action.MEASURE_SELF_READ, Action.MEASURE_REVIEW_REQUEST])
def test_own_review_survives_ban_and_unresolved_other_policies(action):
    facts = AccessFacts(restrictions=(restriction(action, context=RestrictionContext.BOTH),))
    resource = ResourceFacts(ResourceKind.MEASURE, affected_account_id=USER)
    assert decide(
        action, actor=replace(ACTOR, personal_verified=False), resource=resource, facts=facts
    )
    assert not decide(action, resource=replace(resource, affected_account_id=OTHER), facts=facts)
    assert not decide(action, context=ORGANIZATIONAL, resource=resource, facts=facts)


def test_public_read_has_no_unagreed_global_ban():
    facts = AccessFacts(
        restrictions=(restriction(Action.PUBLICATION_PUBLIC_READ, context=RestrictionContext.BOTH),)
    )
    resource = ResourceFacts(
        ResourceKind.PUBLICATION, visibility="visible", status="published", published_at=NOW
    )
    assert decide(Action.PUBLICATION_PUBLIC_READ, context=PUBLIC, resource=resource, facts=facts)


def test_private_read_cannot_be_used_as_publication_mutation_or_opportunity_update():
    resource = ResourceFacts(ResourceKind.PUBLICATION, owner_account_id=USER)
    assert decide(Action.PUBLICATION_MANAGE_READ, resource=resource)
    assert not decide(Action.PUBLICATION_MUTATE, resource=resource)
    resource = replace(resource, kind=ResourceKind.OPPORTUNITY)
    facts = AccessFacts(
        restrictions=(restriction(Action.OPPORTUNITY_UPDATE),),
        configured_conditions=frozenset({Condition.BAN_SCOPE}),
    )
    assert decide(Action.OPPORTUNITY_MANAGE_READ, resource=resource, facts=facts)
    assert not decide(Action.OPPORTUNITY_UPDATE, resource=resource, facts=facts)


def test_current_delegation_is_scoped_and_has_no_technical_role_requirement():
    assert capability()
    assert capability(actor=replace(ACTOR, personal_verified=False))
    assert not capability(scope=Scope(ScopeKind.ACADEMIC, SIBLING))
    assert not capability(scope=Scope(ScopeKind.ACADEMIC, UNIVERSITY))
    assert not capability(scope=Scope(ScopeKind.ACADEMIC, OUTSIDE))
    assert not capability(scope=Scope())
    assert not capability(scope=Scope(ScopeKind.ORGANIZATION, ORG))


@pytest.mark.parametrize(
    "index,changes",
    [
        (0, {"valid_from": NOW + DAY}),
        (0, {"valid_until": NOW}),
        (0, {"ended_at": NOW}),
        (0, {"ended_at": NOW + DAY}),
        (1, {"valid_from": NOW + DAY}),
        (1, {"valid_until": NOW}),
        (1, {"ended_at": NOW}),
        (1, {"granted_by": UUID(int=8)}),
        (1, {"source": GrantSource.ADMINISTRATIVE}),
        (1, {"parent_grant_id": UUID(int=999)}),
        (1, {"capability_code": "academics.researcher.award"}),
        (1, {"valid_from": NOW - 40 * DAY}),
        (1, {"valid_until": NOW + 11 * DAY}),
        (1, {"valid_until": None}),
        (0, {"scope": Scope(ScopeKind.ACADEMIC, SIBLING)}),
    ],
)
def test_delegation_rejects_broken_authority_even_when_child_looks_live(index, changes):
    facts = backing()
    grants = list(facts.grants)
    grants[index] = replace(grants[index], **changes)
    assert not capability(replace(facts, grants=tuple(grants)))


def test_chain_can_be_long_and_revocation_at_any_ancestor_is_effective():
    facts = backing()
    root, middle = facts.grants
    middle = replace(middle, account_id=UUID(int=8))
    leaf = replace(
        middle,
        id=UUID(int=102),
        account_id=USER,
        granted_by=middle.account_id,
        parent_grant_id=middle.id,
        scope=Scope(ScopeKind.ACADEMIC, CAREER),
    )
    extended = replace(facts, grants=(root, middle, leaf))
    assert capability(extended)
    assert not capability(replace(extended, grants=(replace(root, ended_at=NOW), middle, leaf)))


def test_explicit_trust_and_delegability_are_required_and_duplicates_fail_closed():
    facts = backing()
    root, child = facts.grants
    assert not capability(replace(facts, trusted_root_ids=frozenset()))
    assert not capability(
        replace(facts, capabilities=(CapabilityFacts(root.capability_code, False),))
    )
    assert not capability(replace(facts, capabilities=facts.capabilities * 2))
    assert not capability(replace(facts, grants=(root, child, child)))
    assert not capability(replace(facts, academic_scopes=ACADEMIC_SCOPES + (ACADEMIC_SCOPES[0],)))
    assert not capability(
        replace(facts, grants=(replace(root, source=GrantSource.DELEGATION), child))
    )
    # Confiar al hijo por ID no elude la validación de su procedencia y ascendencia.
    assert not capability(replace(facts, grants=(child,), trusted_root_ids=frozenset({CHILD_ID})))


def test_foreign_capability_parent_and_inactive_actor_do_not_authorize():
    facts = backing()
    root, child = facts.grants
    root = replace(root, capability_code="academics.researcher.award")
    assert not capability(replace(facts, grants=(root, child)))
    assert not capability(actor=replace(ACTOR, is_active=False))
    assert not capability(actor=ActorFacts())
    assert not capability(facts={})
    assert not capability(capability_code=["academics.verification.review"])


def test_authority_cycle_has_no_root_even_if_every_node_is_marked_trusted():
    facts = backing()
    root, child = facts.grants
    root = replace(
        root,
        source=GrantSource.DELEGATION,
        parent_grant_id=CHILD_ID,
        granted_by=USER,
        valid_from=child.valid_from,
        valid_until=child.valid_until,
        scope=child.scope,
    )
    assert not capability(
        replace(facts, grants=(root, child), trusted_root_ids=frozenset({ROOT_ID, CHILD_ID}))
    )


@pytest.mark.parametrize(
    "scopes",
    [
        (),
        (
            AcademicScopeFacts(FACULTY, UNIVERSITY, CAREER),
            AcademicScopeFacts(CAREER, UNIVERSITY, FACULTY),
        ),
        (
            AcademicScopeFacts(FACULTY, UNIVERSITY, UUID(int=999)),
            AcademicScopeFacts(CAREER, UNIVERSITY, FACULTY),
        ),
        (AcademicScopeFacts(FACULTY, OUTSIDE), AcademicScopeFacts(CAREER, UNIVERSITY, FACULTY)),
    ],
)
def test_invalid_academic_graph_denies_even_a_global_grant(scopes):
    facts = backing(academic_scopes=scopes)
    assert not capability(facts)
    assert not scope_covers(granted=Scope(), target=Scope(ScopeKind.ACADEMIC, CAREER), facts=facts)


def test_scopes_do_not_mix_org_academic_or_global_and_compare_complete_ancestry():
    facts = backing()
    assert scope_covers(granted=Scope(), target=Scope(ScopeKind.ORGANIZATION, ORG), facts=facts)
    assert scope_covers(
        granted=Scope(ScopeKind.ORGANIZATION, ORG),
        target=Scope(ScopeKind.ORGANIZATION, ORG),
        facts=facts,
    )
    assert not scope_covers(
        granted=Scope(ScopeKind.ORGANIZATION, ORG),
        target=Scope(ScopeKind.ORGANIZATION, OTHER_ORG),
        facts=facts,
    )
    assert not scope_covers(
        granted=Scope(ScopeKind.ACADEMIC, UNIVERSITY), target=Scope(), facts=facts
    )
    assert not scope_covers(granted={}, target=Scope(), facts=facts)


@pytest.mark.parametrize("source", [GrantSource.BOOTSTRAP, GrantSource.ADMINISTRATIVE])
def test_direct_root_works_only_with_explicit_server_trust(source):
    facts = backing()
    root = replace(facts.grants[0], account_id=USER, scope=Scope(), source=source)
    facts = replace(facts, grants=(root,))
    assert capability(facts)
    assert not capability(replace(facts, trusted_root_ids=frozenset()))
    assert capability(facts, now=root.valid_from)  # Intervalo cerrado al inicio.
    assert not capability(facts, now=root.valid_until)  # Abierto al final.


GOVERNMENT_CASES = [
    (
        Action.ACADEMIC_SCOPE_MANAGE,
        "academics.scope.manage",
        ResourceKind.ACADEMIC_SCOPE,
        Condition.ACADEMIC_GOVERNANCE,
    ),
    (
        Action.PERSONAL_VERIFICATION_REVIEW,
        "academics.verification.review",
        ResourceKind.PERSONAL_VERIFICATION,
        None,
    ),
    (
        Action.RESEARCHER_REQUEST,
        "academics.researcher.request",
        ResourceKind.RESEARCHER_REQUEST,
        Condition.RESEARCHER_PROTOCOL,
    ),
    (
        Action.RESEARCHER_AWARD,
        "academics.researcher.award",
        ResourceKind.RESEARCHER_REQUEST,
        Condition.RESEARCHER_PROTOCOL,
    ),
    (
        Action.ORGANIZATION_VERIFICATION_REVIEW,
        "organizations.verification.review",
        ResourceKind.ORGANIZATION_VERIFICATION,
        None,
    ),
    (
        Action.HIGHLIGHT_CREATE,
        "publications.highlight",
        ResourceKind.PUBLICATION,
        Condition.HIGHLIGHT_RULES,
    ),
    (Action.MODERATION_REVIEW, "moderation.review", ResourceKind.REPORT, None),
    (
        Action.DOMAIN_MANAGE,
        "academics.domain.manage",
        ResourceKind.DOMAIN,
        Condition.DOMAIN_GOVERNANCE,
    ),
    (
        Action.RECOVERY_REVIEW,
        "identity.recovery.review",
        ResourceKind.RECOVERY_REQUEST,
        Condition.RECOVERY_PROTOCOL,
    ),
]


def government_facts(code, **changes):
    facts = backing(code)
    root = replace(facts.grants[0], account_id=USER, scope=Scope())
    return replace(facts, grants=(root,), **changes)


@pytest.mark.parametrize("action,code,kind,condition", GOVERNMENT_CASES)
def test_government_requires_exact_capability_scope_and_affected_configuration(
    action, code, kind, condition
):
    academic = kind in (
        ResourceKind.ACADEMIC_SCOPE,
        ResourceKind.PERSONAL_VERIFICATION,
        ResourceKind.RESEARCHER_REQUEST,
    )
    resource = ResourceFacts(kind, scope=Scope(ScopeKind.ACADEMIC, CAREER) if academic else Scope())
    facts = government_facts(code)
    result = decide(action, resource=resource, facts=facts)
    if condition:
        assert result.required_conditions == (condition,)
    else:
        assert result
    facts = replace(facts, configured_conditions=ALL_CONFIGURED)
    assert decide(action, resource=resource, facts=facts)
    assert not decide(action, resource=resource, facts=replace(facts, capabilities=()))
    assert not decide(action, resource=resource, facts=facts, context=ORGANIZATIONAL)
    assert not decide(action, resource=replace(resource, kind=ResourceKind.DIRECTORY), facts=facts)


def test_ban_requires_scope_and_operational_review_separately_from_report_review():
    facts = government_facts("moderation.review")
    resource = ResourceFacts(ResourceKind.REPORT)
    assert decide(Action.MODERATION_REVIEW, resource=resource, facts=facts)
    result = decide(Action.BAN_APPLY, resource=resource, facts=facts)
    assert result.required_conditions == (Condition.BAN_SCOPE, Condition.BAN_REVIEW_READY)
    partial = replace(facts, configured_conditions=frozenset({Condition.BAN_SCOPE}))
    assert decide(Action.BAN_APPLY, resource=resource, facts=partial).required_conditions == (
        Condition.BAN_REVIEW_READY,
    )
    assert decide(
        Action.BAN_APPLY,
        resource=resource,
        facts=replace(facts, configured_conditions=ALL_CONFIGURED),
    )


def test_audit_needs_scope_and_explicit_decision_type_and_not_just_a_capability():
    facts = government_facts("audit.read")
    resource = ResourceFacts(ResourceKind.AUDIT_EVENT, audit_type="moderation.decision")
    assert (
        decide(Action.AUDIT_READ, resource=resource, facts=facts).code
        is DecisionCode.AUDIT_TYPE_DENIED
    )
    facts = replace(facts, allowed_audit_types=frozenset({"moderation.decision"}))
    assert decide(Action.AUDIT_READ, resource=resource, facts=facts)
    assert not decide(
        Action.AUDIT_READ, resource=replace(resource, audit_type="identity.recovery"), facts=facts
    )
    scoped = backing("audit.read", allowed_audit_types=facts.allowed_audit_types)
    assert decide(
        Action.AUDIT_READ,
        resource=replace(resource, scope=Scope(ScopeKind.ACADEMIC, CAREER)),
        facts=scoped,
    )
    assert not decide(
        Action.AUDIT_READ,
        resource=replace(resource, scope=Scope(ScopeKind.ACADEMIC, OUTSIDE)),
        facts=scoped,
    )


def test_pure_decision_is_deterministic_and_timezone_preserves_instant():
    facts = backing()
    before = repr(facts)
    decision = capability(facts)
    assert decision == capability(facts, now=NOW.astimezone(timezone(timedelta(hours=-5))))
    assert repr(facts) == before
    assert not bool(AccessDecision(False, DecisionCode.DEFAULT_DENY))
    with pytest.raises(FrozenInstanceError):
        facts.grants[0].ended_at = NOW
    with pytest.raises(FrozenInstanceError):
        decision.allowed = False


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ActorFacts("untrusted-id"),
        lambda: ActorFacts(USER, is_active="yes"),
        lambda: ContextFacts("personal"),
        lambda: ContextFacts(ContextKind.ORGANIZATION),
        lambda: Scope(ScopeKind.GLOBAL, ORG),
        lambda: AccessFacts(grants=[]),
        lambda: AccessFacts(configured_conditions=frozenset({"PB01"})),
        lambda: AccessFacts(trusted_root_ids=frozenset({"client-root"})),
        lambda: AccessFacts(allowed_audit_types=frozenset({""})),
        lambda: ResourceFacts(
            ResourceKind.OPPORTUNITY, owner_account_id=USER, owner_organization_id=ORG
        ),
        lambda: replace(REPRESENTATION, created_at=datetime(2026, 1, 1)),
    ],
)
def test_contracts_reject_ambiguous_and_mutable_facts(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_policies_import_and_execute_without_django_http_database_or_site_packages():
    backend = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    script = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(backend)!r})",
            "from datetime import UTC, datetime",
            "from modules.access.contracts import *",
            "from modules.access.policies import authorize",
            "decision = authorize(action='unknown', actor=ActorFacts(), context=ContextFacts(ContextKind.PUBLIC), resource=ResourceFacts(ResourceKind.DIRECTORY), facts=AccessFacts(), now=datetime(2026, 11, 7, tzinfo=UTC))",
            "assert not decision",
            "assert not any(name.split('.')[0] in {'django', 'psycopg', 'rest_framework', 'http', 'socket'} for name in sys.modules)",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    for path in (
        backend / "modules/access/policies.py",
        backend / "modules/access/contracts/__init__.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Prohíbe leer el reloj, entorno o E/S, incluso aunque nadie ejercitara esa rama.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "now",
                    "today",
                    "execute",
                    "connect",
                    "getenv",
                    "read_text",
                    "write_text",
                }
