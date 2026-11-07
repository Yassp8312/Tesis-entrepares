"""Integración de hechos derivados, selectores mínimos y siete FK compuestas."""

from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader

from modules.academics.models import (
    AcademicScope,
    Discipline,
    Institution,
    InstitutionalDomain,
    PersonalVerification,
)
from modules.academics.selectors import get_personal_verification
from modules.identity.models import Account, EmailChallenge
from modules.opportunities.models import Funding, Opportunity
from modules.opportunities.selectors import get_opportunity_funding
from modules.organizations.models import Organization, OrganizationVerification, Representation
from modules.organizations.selectors import get_organization_verification
from modules.profiles.models import Contact, Education, Profile
from modules.profiles.selectors import get_profile_completeness

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
START = datetime(2026, 1, 1, tzinfo=UTC)
VIEWS = {
    "model_profile_completeness": (
        "profiles",
        "0002_profile_completeness_view",
        "0001_profiles_and_education",
        {"profile_id": "uuid", "account_id": "uuid", "is_complete": "boolean"},
    ),
    "model_personal_verification": (
        "academics",
        "0003_personal_verification_view",
        "0002_personal_verifications_and_researcher_awards",
        {"account_id": "uuid", "is_verified": "boolean"},
    ),
    "model_organization_verification": (
        "organizations",
        "0002_organization_verification_view",
        "0001_organizations_and_representation",
        {"organization_id": "uuid", "is_verified": "boolean"},
    ),
    "model_opportunity_funding": (
        "opportunities",
        "0002_opportunity_funding_view",
        "0001_opportunities_and_funding",
        {"opportunity_id": "uuid", "is_funded": "boolean"},
    ),
}
COMPOSITES = [
    (
        "academics_scope",
        ("parent_id", "institution_id"),
        "fk_t09_02",
        "academics_scope",
        ("id", "institution_id"),
    ),
    (
        "academics_personal_verification",
        ("challenge_id", "account_id"),
        "fk_t12_02",
        "identity_email_challenge",
        ("id", "account_id"),
    ),
    (
        "academics_researcher_award",
        ("source_request_id", "account_id", "academic_scope_id"),
        "fk_t14_05",
        "academics_researcher_request",
        ("id", "account_id", "academic_scope_id"),
    ),
    (
        "publications_event_detail",
        ("publication_id", "publication_kind"),
        "fk_t24_01",
        "publications_publication",
        ("id", "kind"),
    ),
    (
        "moderation_review_request",
        ("measure_id", "requested_by"),
        "fk_t30_01",
        "moderation_measure",
        ("id", "account_id"),
    ),
    (
        "access_grant",
        ("parent_grant_id", "granted_by"),
        "fk_t33_07",
        "access_grant",
        ("id", "account_id"),
    ),
    (
        "notifications_notice",
        ("opportunity_id", "validity_revision"),
        "fk_t34_01",
        "opportunities_lifecycle_event",
        ("opportunity_id", "validity_revision"),
    ),
]
SOURCE_KEYS = [
    ("academics_scope", ("institution_id",), "fk_t09_01", "academics_institution", ("id",)),
    (
        "academics_scope",
        ("parent_id", "institution_id"),
        "fk_t09_02",
        "academics_scope",
        ("id", "institution_id"),
    ),
    ("academics_personal_verification", ("account_id",), "fk_t12_01", "identity_account", ("id",)),
    (
        "academics_personal_verification",
        ("challenge_id", "account_id"),
        "fk_t12_02",
        "identity_email_challenge",
        ("id", "account_id"),
    ),
    ("academics_personal_verification", ("domain_id",), "fk_t12_03", "academics_domain", ("id",)),
    (
        "academics_personal_verification",
        ("academic_scope_id",),
        "fk_t12_04",
        "academics_scope",
        ("id",),
    ),
    ("academics_personal_verification", ("decided_by",), "fk_t12_05", "identity_account", ("id",)),
    ("academics_researcher_award", ("account_id",), "fk_t14_01", "identity_account", ("id",)),
    ("academics_researcher_award", ("awarded_by",), "fk_t14_02", "identity_account", ("id",)),
    ("academics_researcher_award", ("ended_by",), "fk_t14_03", "identity_account", ("id",)),
    ("academics_researcher_award", ("academic_scope_id",), "fk_t14_04", "academics_scope", ("id",)),
    (
        "academics_researcher_award",
        ("source_request_id", "account_id", "academic_scope_id"),
        "fk_t14_05",
        "academics_researcher_request",
        ("id", "account_id", "academic_scope_id"),
    ),
    (
        "publications_event_detail",
        ("publication_id", "publication_kind"),
        "fk_t24_01",
        "publications_publication",
        ("id", "kind"),
    ),
    (
        "moderation_review_request",
        ("measure_id", "requested_by"),
        "fk_t30_01",
        "moderation_measure",
        ("id", "account_id"),
    ),
    ("access_grant", ("account_id",), "fk_t33_01", "identity_account", ("id",)),
    ("access_grant", ("granted_by",), "fk_t33_02", "identity_account", ("id",)),
    ("access_grant", ("ended_by",), "fk_t33_03", "identity_account", ("id",)),
    ("access_grant", ("capability_code",), "fk_t33_04", "access_capability", ("code",)),
    ("access_grant", ("academic_scope_id",), "fk_t33_05", "academics_scope", ("id",)),
    ("access_grant", ("organization_id",), "fk_t33_06", "organizations_organization", ("id",)),
    (
        "access_grant",
        ("parent_grant_id", "granted_by"),
        "fk_t33_07",
        "access_grant",
        ("id", "account_id"),
    ),
    (
        "notifications_notice",
        ("opportunity_id", "validity_revision"),
        "fk_t34_01",
        "opportunities_lifecycle_event",
        ("opportunity_id", "validity_revision"),
    ),
]
ORM_COMPOSITE_FIELDS = [
    ("academics", "AcademicScope", "parent"),
    ("academics", "PersonalVerification", "challenge"),
    ("academics", "ResearcherAward", "source_request"),
    ("publications", "EventDetail", "publication"),
    ("moderation", "ReviewRequest", "measure"),
    ("moderation", "ReviewRequest", "requested_by"),
    ("access", "Grant", "parent_grant"),
    ("notifications", "Notice", "opportunity"),
]


@pytest.fixture
def records():
    actor = Account.objects.create_user("vistas-actor@example.org")
    subject = Account.objects.create_user("vistas-persona@example.org")
    institution = Institution.objects.create(
        name="Institución sintética", kind="university", origin="declared"
    )
    scope = AcademicScope.objects.create(
        institution=institution, name="Ámbito sintético", kind="faculty"
    )
    discipline = Discipline.objects.create(name="Disciplina sintética", origin="declared")
    profile = Profile.objects.create(
        account=subject, full_name="Nombre sintético privado", bio="Biografía sintética privada"
    )
    organization = Organization.objects.create(
        name="Entidad sintética", kind="other", created_by=actor
    )
    opportunity = Opportunity.objects.create(
        owner_account=subject,
        author=subject,
        title="Proyecto sintético privado",
        description="Descripción sintética privada",
        area="Área sintética",
        responsible_label="Responsable sintético",
    )
    return SimpleNamespace(
        actor=actor,
        subject=subject,
        institution=institution,
        scope=scope,
        discipline=discipline,
        profile=profile,
        organization=organization,
        opportunity=opportunity,
    )


def education(r, ended=False):
    return Education.objects.create(
        profile=r.profile,
        institution=r.institution,
        discipline=r.discipline,
        condition="student",
        ended_at=START if ended else None,
    )


def contact(r, visible=True):
    return Contact.objects.create(
        profile=r.profile, kind="email", value="privado-sintetico@example.org", is_visible=visible
    )


def personal_verification(r, status="approved"):
    return PersonalVerification.objects.create(
        account=r.subject,
        method="manual",
        academic_scope=r.scope,
        status=status,
        decided_by=r.actor if status != "pending" else None,
        decided_at=START if status != "pending" else None,
        decision_reason="Motivo sintético privado" if status != "pending" else None,
    )


def organization_verification(r, status="approved"):
    return OrganizationVerification.objects.create(
        organization=r.organization,
        requested_by=r.actor,
        status=status,
        decided_by=r.actor if status != "pending" else None,
        decided_at=START if status != "pending" else None,
        decision_reason="Motivo sintético privado" if status != "pending" else None,
    )


@pytest.mark.parametrize("view", VIEWS)
def test_four_normal_views_have_only_specified_columns_and_no_materialized_storage(view):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relkind FROM pg_class WHERE oid=%s::regclass", [view])
        assert cursor.fetchone() == ("v",)
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum",
            [view],
        )
        assert dict(cursor.fetchall()) == VIEWS[view][3]


def test_all_seven_composite_keys_and_their_simple_companions_match_design():
    tables = sorted({row[0] for row in COMPOSITES})
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid=ANY(%s::regclass[]) AND contype='f'",
            [tables],
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE connamespace=current_schema()::regnamespace AND contype='f' AND cardinality(conkey)>1"
        )
        assert {name for (name,) in cursor} == {row[2] for row in COMPOSITES}
    assert {(table, name): definition for table, name, definition, *_ in rows} == {
        (
            table,
            name,
        ): f"FOREIGN KEY ({', '.join(fields)}) REFERENCES {target}({', '.join(keys)}) ON DELETE RESTRICT"
        for table, fields, name, target, keys in SOURCE_KEYS
    }
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )
    state = MigrationLoader(None).project_state().apps
    from django.apps import apps

    for owner, model, field in ORM_COMPOSITE_FIELDS:
        assert not apps.get_model(owner, model)._meta.get_field(field).db_constraint
        assert not state.get_model(owner, model)._meta.get_field(field).db_constraint


@pytest.mark.parametrize("formation", ["missing", "ended", "current"])
@pytest.mark.parametrize("channel", ["missing", "hidden", "visible"])
def test_completeness_combines_current_education_and_visible_contact(records, formation, channel):
    if formation != "missing":
        education(records, formation == "ended")
    if channel != "missing":
        contact(records, channel == "visible")
    result = get_profile_completeness(profile_id=records.profile.pk)
    assert result.is_complete == (formation == "current" and channel == "visible")
    assert not get_personal_verification(account_id=records.subject.pk).is_verified


def test_completeness_is_live_and_does_not_multiply_profile_for_multiple_children(records):
    current = education(records)
    visible = contact(records)
    other = Discipline.objects.create(name="Otra disciplina sintética", origin="declared")
    Education.objects.create(
        profile=records.profile,
        institution=records.institution,
        discipline=other,
        condition="graduate",
    )
    Contact.objects.create(
        profile=records.profile, kind="telegram", value="contacto-sintetico", is_visible=False
    )
    assert get_profile_completeness(profile_id=records.profile.pk).is_complete
    current.ended_at = START
    current.save(update_fields={"ended_at"})
    assert get_profile_completeness(profile_id=records.profile.pk).is_complete
    visible.is_visible = False
    visible.save(update_fields={"is_visible"})
    assert not get_profile_completeness(profile_id=records.profile.pk).is_complete
    visible.is_visible = True
    visible.save(update_fields={"is_visible"})
    assert get_profile_completeness(profile_id=records.profile.pk).is_complete
    visible.delete()
    assert not get_profile_completeness(profile_id=records.profile.pk).is_complete
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM model_profile_completeness WHERE profile_id=%s",
            [records.profile.pk],
        )
        assert cursor.fetchone() == (1,)


@pytest.mark.parametrize("status", ["pending", "approved", "rejected", "withdrawn"])
def test_personal_verification_requires_an_approved_backing(records, status):
    personal_verification(records, status)
    assert get_personal_verification(account_id=records.subject.pk).is_verified == (
        status == "approved"
    )
    assert not get_personal_verification(account_id=records.actor.pk).is_verified


def test_personal_view_uses_any_approved_backing_instead_of_last_request(records):
    first = personal_verification(records)
    second = personal_verification(records)
    personal_verification(records, "pending")
    first.status = "withdrawn"
    first.save(update_fields={"status"})
    assert get_personal_verification(account_id=records.subject.pk).is_verified
    second.status = "withdrawn"
    second.save(update_fields={"status"})
    assert not get_personal_verification(account_id=records.subject.pk).is_verified


def test_backing_survives_education_email_and_domain_changes_without_conferring_new_affiliation(
    records,
):
    formation = education(records)
    contact(records)
    domain = InstitutionalDomain.objects.create(
        domain_ascii="example.org",
        institution=records.institution,
        status="recognized",
        evidence_reference="referencia-sintetica-privada",
        decided_by=records.actor,
        decided_at=START,
    )
    challenge = EmailChallenge.objects.create(
        account=records.subject,
        purpose="email_confirmation",
        email_snapshot=records.subject.email,
        created_at=START,
        expires_at=START + timedelta(days=1),
        consumed_at=START + timedelta(minutes=1),
    )
    PersonalVerification.objects.create(
        account=records.subject,
        method="institutional_email",
        challenge=challenge,
        domain=domain,
        status="approved",
        decided_at=START + timedelta(minutes=2),
        decision_reason="Aprobación sintética",
    )
    formation.ended_at = START
    formation.save(update_fields={"ended_at"})
    records.subject.email = "otra-direccion-sintetica@example.net"
    records.subject.save(update_fields={"email"})
    domain.status = "withdrawn"
    domain.save(update_fields={"status"})
    assert get_personal_verification(account_id=records.subject.pk).is_verified
    assert not get_profile_completeness(profile_id=records.profile.pk).is_complete
    records.subject.is_active = False
    records.subject.save(update_fields={"is_active"})
    assert get_personal_verification(account_id=records.subject.pk).is_verified


@pytest.mark.parametrize("status", ["pending", "approved", "rejected", "withdrawn"])
def test_organization_verification_requires_approved_record(records, status):
    organization_verification(records, status)
    assert get_organization_verification(organization_id=records.organization.pk).is_verified == (
        status == "approved"
    )


def test_organization_backing_is_separate_from_representative_personal_status(records):
    backing = organization_verification(records)
    representation = Representation.objects.create(
        account=records.subject,
        organization=records.organization,
        granted_by=records.actor,
        created_at=START,
    )
    assert get_organization_verification(organization_id=records.organization.pk).is_verified
    assert not get_personal_verification(account_id=records.subject.pk).is_verified
    representation.revoked_at = START
    representation.revoked_by = records.actor
    representation.save(update_fields={"revoked_at", "revoked_by"})
    assert get_organization_verification(organization_id=records.organization.pk).is_verified
    backing.status = "withdrawn"
    backing.save(update_fields={"status"})
    assert not get_organization_verification(organization_id=records.organization.pk).is_verified


def test_organization_uses_existing_approved_record_when_other_requests_change(records):
    first = organization_verification(records)
    second = organization_verification(records)
    organization_verification(records, "rejected")
    first.status = "withdrawn"
    first.save(update_fields={"status"})
    assert get_organization_verification(organization_id=records.organization.pk).is_verified
    second.status = "withdrawn"
    second.save(update_fields={"status"})
    assert not get_organization_verification(organization_id=records.organization.pk).is_verified


def test_funding_is_live_and_follows_presence_including_zero_estimate(records):
    assert not get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded
    funding = Funding.objects.create(
        opportunity=records.opportunity,
        estimated_amount=Decimal("0.00"),
        currency_code="CUP",
        coverage="project",
        payment_kind="one_off",
    )
    assert get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded
    records.opportunity.visibility = "hidden"
    records.opportunity.save(update_fields={"visibility"})
    assert get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded
    funding.delete()
    assert not get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded


SELECTORS = [
    (
        get_profile_completeness,
        "profile_id",
        "profile",
        {"profile_id", "account_id", "is_complete"},
    ),
    (get_personal_verification, "account_id", "subject", {"account_id", "is_verified"}),
    (
        get_organization_verification,
        "organization_id",
        "organization",
        {"organization_id", "is_verified"},
    ),
    (get_opportunity_funding, "opportunity_id", "opportunity", {"opportunity_id", "is_funded"}),
]


@pytest.mark.parametrize("selector,key,record,fields", SELECTORS)
def test_selectors_return_only_immutable_minimum_dto_in_one_query(
    records, django_assert_num_queries, selector, key, record, fields
):
    with django_assert_num_queries(1):
        result = selector(**{key: getattr(records, record).pk})
    assert set(asdict(result)) == fields
    assert "privado" not in repr(result) and "example.org" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        setattr(result, next(iter(fields)), None)


@pytest.mark.parametrize("selector,key,record,fields", SELECTORS)
def test_missing_resource_returns_none_instead_of_false_or_another_resource(
    selector, key, record, fields
):
    assert selector(**{key: uuid4()}) is None


def test_views_follow_transaction_and_rollback_instead_of_stored_editable_flags(records):
    education(records)
    contact(records)
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            personal_verification(records)
            organization_verification(records)
            Funding.objects.create(
                opportunity=records.opportunity,
                estimated_amount=1,
                currency_code="CUP",
                coverage="project",
                payment_kind="one_off",
            )
            assert get_personal_verification(account_id=records.subject.pk).is_verified
            assert get_organization_verification(
                organization_id=records.organization.pk
            ).is_verified
            assert get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded
            raise RuntimeError("fallo sintético de coordinación")
    assert not get_personal_verification(account_id=records.subject.pk).is_verified
    assert not get_organization_verification(organization_id=records.organization.pk).is_verified
    assert not get_opportunity_funding(opportunity_id=records.opportunity.pk).is_funded
    assert get_profile_completeness(profile_id=records.profile.pk).is_complete


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("view", VIEWS)
def test_view_migration_reverses_without_cascade_or_data_loss_and_restores_graph(records, view):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    owner, migration, previous, _ = VIEWS[view]
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([(owner, previous)])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT viewname FROM pg_views WHERE schemaname=current_schema() AND viewname=ANY(%s)",
                [list(VIEWS)],
            )
            assert {name for (name,) in cursor} == set(VIEWS) - {view}
        assert (
            Profile.objects.filter(pk=records.profile.pk).exists()
            and Account.objects.filter(pk=records.subject.pk).exists()
        )
        assert set(connection.introspection.table_names()) == tables
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert not MigrationExecutor(connection).migration_plan(targets)
    test_four_normal_views_have_only_specified_columns_and_no_materialized_storage(view)
    test_all_seven_composite_keys_and_their_simple_companions_match_design()
