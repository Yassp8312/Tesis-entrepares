"""T12–T14: claves compuestas e historial; no acredita revisión institucional real."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.academics.models import (
    AcademicScope,
    Institution,
    InstitutionalDomain,
    PersonalVerification,
    ResearcherAward,
    ResearcherRequest,
)
from modules.identity.models import Account, EmailChallenge

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
DECIDED = CREATED + timedelta(hours=1)
COMMON = {
    "id": ("uuid", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
SCHEMA = {
    "academics_personal_verification": {
        **COMMON,
        "account_id": ("uuid", False),
        "method": ("character varying(24)", False),
        "status": ("character varying(16)", False),
        "challenge_id": ("uuid", True),
        "domain_id": ("uuid", True),
        "academic_scope_id": ("uuid", True),
        "evidence_reference": ("text", True),
        "decided_by": ("uuid", True),
        "decided_at": ("timestamp with time zone", True),
        "decision_reason": ("text", True),
    },
    "academics_researcher_request": {
        **COMMON,
        "account_id": ("uuid", False),
        "academic_scope_id": ("uuid", False),
        "requested_by": ("uuid", False),
        "justification": ("text", False),
        "decision": ("character varying(16)", False),
        "decided_by": ("uuid", True),
        "decided_at": ("timestamp with time zone", True),
        "decision_reason": ("text", True),
    },
    "academics_researcher_award": {
        **COMMON,
        "account_id": ("uuid", False),
        "academic_scope_id": ("uuid", False),
        "source_request_id": ("uuid", True),
        "awarded_by": ("uuid", False),
        "justification": ("text", False),
        "ended_at": ("timestamp with time zone", True),
        "ended_by": ("uuid", True),
    },
}
MODELS = [PersonalVerification, ResearcherRequest, ResearcherAward]
REFERENCES = [
    ("academics_personal_verification", "account_id", "fk_t12_01", "identity_account"),
    ("academics_personal_verification", "challenge_id", "fk_t12_02", "identity_email_challenge"),
    ("academics_personal_verification", "domain_id", "fk_t12_03", "academics_domain"),
    ("academics_personal_verification", "academic_scope_id", "fk_t12_04", "academics_scope"),
    ("academics_personal_verification", "decided_by", "fk_t12_05", "identity_account"),
    ("academics_researcher_request", "account_id", "fk_t13_01", "identity_account"),
    ("academics_researcher_request", "requested_by", "fk_t13_02", "identity_account"),
    ("academics_researcher_request", "decided_by", "fk_t13_03", "identity_account"),
    ("academics_researcher_request", "academic_scope_id", "fk_t13_04", "academics_scope"),
    ("academics_researcher_award", "account_id", "fk_t14_01", "identity_account"),
    ("academics_researcher_award", "awarded_by", "fk_t14_02", "identity_account"),
    ("academics_researcher_award", "ended_by", "fk_t14_03", "identity_account"),
    ("academics_researcher_award", "academic_scope_id", "fk_t14_04", "academics_scope"),
    (
        "academics_researcher_award",
        "source_request_id",
        "fk_t14_05",
        "academics_researcher_request",
    ),
]


def insert_row(table, values):
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.Placeholder() for _ in values),
            ),
            list(values.values()),
        )
        return cursor.fetchone()[0]


def assert_rejected(table, values, constraint):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            insert_row(table, values)
    assert error.value.__cause__.diag.constraint_name == constraint


@pytest.fixture
def records():
    account, other, reviewer, free_account = [
        Account.objects.create_user(f"respaldo-{name}@example.org")
        for name in ("persona", "otra", "revisor", "libre")
    ]
    institution = Institution.objects.create(
        name="Institución sintética", kind="university", origin="curated"
    )
    scope, other_scope, free_scope = [
        AcademicScope.objects.create(
            institution=institution, name=f"Ámbito sintético {name}", kind="faculty"
        )
        for name in ("A", "B", "libre")
    ]
    domain = InstitutionalDomain.objects.create(
        institution=institution,
        domain_ascii="example.org",
        status="recognized",
        evidence_reference="Respaldo sintético, sin validez institucional",
        decided_by=reviewer,
        decided_at=DECIDED,
    )
    challenge, other_challenge = [
        EmailChallenge.objects.create(
            account=person,
            purpose="email_confirmation",
            email_snapshot=person.email,
            created_at=CREATED,
            expires_at=CREATED + timedelta(days=1),
            consumed_at=DECIDED,
        )
        for person in (account, other)
    ]
    request = ResearcherRequest.objects.create(
        account=account,
        academic_scope=scope,
        requested_by=reviewer,
        justification="Propuesta sintética",
        decision="approved",
        decided_by=reviewer,
        decided_at=DECIDED,
        decision_reason="Decisión sintética",
    )
    return SimpleNamespace(
        account=account,
        other=other,
        reviewer=reviewer,
        free_account=free_account,
        institution=institution,
        scope=scope,
        other_scope=other_scope,
        free_scope=free_scope,
        domain=domain,
        challenge=challenge,
        other_challenge=other_challenge,
        request=request,
    )


def valid_values(table, records):
    return {
        "academics_personal_verification": {
            "account_id": records.account.pk,
            "method": "manual",
            "academic_scope_id": records.scope.pk,
        },
        "academics_researcher_request": {
            "account_id": records.account.pk,
            "academic_scope_id": records.scope.pk,
            "requested_by": records.reviewer.pk,
            "justification": "Propuesta sintética",
        },
        "academics_researcher_award": {
            "account_id": records.account.pk,
            "academic_scope_id": records.scope.pk,
            "awarded_by": records.reviewer.pk,
            "justification": "Concesión sintética",
        },
    }[table]


def email_values(records):
    return {
        "account_id": records.account.pk,
        "method": "institutional_email",
        "challenge_id": records.challenge.pk,
        "domain_id": records.domain.pk,
    }


def decided_values(table, records, state="approved"):
    return {
        **valid_values(table, records),
        "status" if table.endswith("verification") else "decision": state,
        "decided_by": records.reviewer.pk,
        "decided_at": DECIDED,
        "decision_reason": "Decisión sintética",
    }


@pytest.mark.parametrize(
    "table,prefix,count,indexes",
    [
        (
            "academics_personal_verification",
            "t12",
            6,
            {
                "uq_t12_01": ["challenge_id"],
                "uq_t12_02": ["account_id"],
                "ix_t12_03": ["account_id", "status"],
                "ix_t12_04": ["challenge_id", "account_id"],
                "ix_t12_05": ["domain_id"],
                "ix_t12_06": ["academic_scope_id"],
                "ix_t12_07": ["decided_by"],
            },
        ),
        (
            "academics_researcher_request",
            "t13",
            3,
            {
                "uq_t13_key01": ["id", "account_id", "academic_scope_id"],
                "ix_t13_01": ["account_id"],
                "ix_t13_02": ["requested_by"],
                "ix_t13_03": ["decided_by"],
                "ix_t13_04": ["academic_scope_id"],
            },
        ),
        (
            "academics_researcher_award",
            "t14",
            2,
            {
                "uq_t14_key01": ["source_request_id"],
                "uq_t14_01": ["account_id", "academic_scope_id"],
                "ix_t14_02": ["account_id"],
                "ix_t14_03": ["awarded_by"],
                "ix_t14_04": ["ended_by"],
                "ix_t14_05": ["academic_scope_id"],
                "ix_t14_06": ["source_request_id", "account_id", "academic_scope_id"],
            },
        ),
    ],
)
def test_exact_schema_checks_and_all_indexed_keys(table, prefix, count, indexes):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",
            [table],
        )
        assert {name: (kind, nullable) for name, kind, nullable in cursor} == SCHEMA[table]
        constraints = connection.introspection.get_constraints(cursor, table)
    assert {k for k, v in constraints.items() if v["check"]} == {
        f"ck_{prefix}_{n:02}" for n in range(1, count + 1)
    }
    assert {
        k: v["columns"]
        for k, v in constraints.items()
        if (v["index"] or v["unique"]) and not v["primary_key"]
    } == indexes
    assert {k for k, v in constraints.items() if v["unique"] and not v["primary_key"]} == {
        "t12": {"uq_t12_01", "uq_t12_02"},
        "t13": {"uq_t13_key01"},
        "t14": {"uq_t14_key01", "uq_t14_01"},
    }[prefix]


def test_unique_predicates_and_nulls_distinct_allow_direct_awards():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexrelid::regclass::text,indisunique,indisvalid,indisready,indnullsnotdistinct,pg_get_expr(indpred,indrelid) FROM pg_index WHERE indexrelid IN ('uq_t12_01'::regclass,'uq_t12_02'::regclass,'uq_t13_key01'::regclass,'uq_t14_01'::regclass,'uq_t14_key01'::regclass) ORDER BY indexrelid::regclass::text"
        )
        rows = cursor.fetchall()
    assert all(
        (unique, valid, ready, nulls_not_distinct) == (True, True, True, False)
        for _, unique, valid, ready, nulls_not_distinct, _ in rows
    )
    predicates = {
        name: expr.replace("(", "").replace(")", "") if expr else None for name, *_, expr in rows
    }
    assert predicates == {
        "uq_t12_01": "challenge_id IS NOT NULL",
        "uq_t12_02": "method::text = 'manual'::text AND status::text = 'pending'::text",
        "uq_t13_key01": None,
        "uq_t14_01": "ended_at IS NULL",
        "uq_t14_key01": None,
    }


def test_fourteen_named_restrict_foreign_keys_include_exact_composite_keys():
    expected = {
        name: (table, f"FOREIGN KEY ({field}) REFERENCES {target}(id) ON DELETE RESTRICT")
        for table, field, name, target in REFERENCES
    }
    expected["fk_t12_02"] = (
        "academics_personal_verification",
        "FOREIGN KEY (challenge_id, account_id) REFERENCES identity_email_challenge(id, account_id) ON DELETE RESTRICT",
    )
    expected["fk_t14_05"] = (
        "academics_researcher_award",
        "FOREIGN KEY (source_request_id, account_id, academic_scope_id) REFERENCES academics_researcher_request(id, account_id, academic_scope_id) ON DELETE RESTRICT",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,conrelid::regclass::text,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid IN ('academics_personal_verification'::regclass,'academics_researcher_request'::regclass,'academics_researcher_award'::regclass) AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: (table, definition) for name, table, definition, *_ in rows} == expected
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


@pytest.mark.parametrize("model", MODELS)
def test_defaults_private_representation_and_partial_save(model, records):
    table = model._meta.db_table
    identifier = insert_row(table, valid_values(table, records))
    record = model.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(record) == str(identifier)
    assert record.created_at == record.updated_at and record.created_at.utcoffset() == timedelta(0)
    if model is PersonalVerification:
        assert (
            record.status == "pending"
            and record.decided_at is None
            and record.decided_by_id is None
        )
        field, value = "evidence_reference", "Referencia sintética privada"
    elif model is ResearcherRequest:
        assert record.decision == "pending" and record.decided_at is None
        field, value = "justification", "Propuesta sintética actualizada"
    else:
        assert (
            record.source_request_id is None
            and record.ended_at is None
            and record.ended_by_id is None
        )
        field, value = "justification", "Concesión sintética actualizada"
    model.objects.filter(pk=identifier).update(updated_at=CREATED)
    setattr(record, field, value)
    record.save(update_fields=[field])
    record.refresh_from_db()
    assert record.updated_at > CREATED and getattr(record, field) == value


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("academics_personal_verification", {"method": "invalid"}, "ck_t12_01"),
        ("academics_personal_verification", {"status": "invalid"}, "ck_t12_02"),
        ("academics_personal_verification", {"decided_at": DECIDED}, "ck_t12_03"),
        ("academics_personal_verification", {"decided_by": "reviewer"}, "ck_t12_03"),
        ("academics_researcher_request", {"justification": ""}, "ck_t13_01"),
        ("academics_researcher_request", {"justification": "   "}, "ck_t13_01"),
        ("academics_researcher_request", {"decision": "invalid"}, "ck_t13_02"),
        ("academics_researcher_award", {"justification": ""}, "ck_t14_01"),
        ("academics_researcher_award", {"justification": "   "}, "ck_t14_01"),
        ("academics_researcher_award", {"ended_at": DECIDED}, "ck_t14_02"),
        ("academics_researcher_award", {"ended_by": "reviewer"}, "ck_t14_02"),
    ],
)
def test_checks_reject_raw_sql(records, table, changes, constraint):
    changes = {k: records.reviewer.pk if v == "reviewer" else v for k, v in changes.items()}
    assert_rejected(table, {**valid_values(table, records), **changes}, constraint)


@pytest.mark.parametrize(
    "route,field,replacement",
    [
        ("manual", "challenge_id", "challenge"),
        ("manual", "domain_id", "domain"),
        ("manual", "academic_scope_id", None),
        ("email", "challenge_id", None),
        ("email", "domain_id", None),
        ("email", "academic_scope_id", "scope"),
    ],
)
def test_email_and_manual_routes_are_exclusive_and_require_their_references(
    records, route, field, replacement
):
    values = (
        valid_values("academics_personal_verification", records)
        if route == "manual"
        else email_values(records)
    )
    assert_rejected(
        "academics_personal_verification",
        {**values, field: getattr(records, replacement).pk if replacement else None},
        "ck_t12_04",
    )


@pytest.mark.parametrize("status", ["approved", "rejected", "withdrawn"])
@pytest.mark.parametrize(
    "missing,constraint",
    [
        ("decided_at", "ck_t12_03"),
        ("decision_reason", "ck_t12_05"),
        ("empty_reason", "ck_t12_05"),
        ("decided_by", "ck_t12_06"),
    ],
)
def test_manual_decision_requires_date_reason_and_human_reviewer(
    records, status, missing, constraint
):
    values = decided_values("academics_personal_verification", records, status)
    values["decision_reason" if missing == "empty_reason" else missing] = (
        "   " if missing == "empty_reason" else None
    )
    assert_rejected("academics_personal_verification", values, constraint)


@pytest.mark.parametrize("status", ["approved", "rejected", "withdrawn"])
def test_complete_manual_decisions_are_stored_without_granting_technical_privileges(
    records, status
):
    identifier = insert_row(
        "academics_personal_verification",
        decided_values("academics_personal_verification", records, status),
    )
    assert PersonalVerification.objects.get(pk=identifier).status == status
    records.account.refresh_from_db()
    assert (
        not records.account.has_usable_password()
        and not records.account.is_staff
        and not records.account.is_superuser
    )


def test_email_approval_allows_no_human_reviewer_and_cannot_reuse_the_challenge(records):
    values = {
        **email_values(records),
        "status": "approved",
        "decided_at": DECIDED,
        "decision_reason": "Consumo sintético",
    }
    identifier = insert_row("academics_personal_verification", values)
    assert PersonalVerification.objects.get(pk=identifier).decided_by_id is None
    assert_rejected("academics_personal_verification", email_values(records), "uq_t12_01")


def test_manual_pending_is_unique_across_scopes_and_can_be_requested_again_after_resolution(
    records,
):
    table = "academics_personal_verification"
    values = valid_values(table, records)
    first = insert_row(table, values)
    assert_rejected(table, {**values, "academic_scope_id": records.other_scope.pk}, "uq_t12_02")
    PersonalVerification.objects.filter(pk=first).update(
        status="rejected",
        decided_by=records.reviewer,
        decided_at=DECIDED,
        decision_reason="Decisión sintética",
    )
    second = insert_row(table, values)
    assert first != second
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            PersonalVerification.objects.filter(pk=first).update(
                status="pending", decided_by=None, decided_at=None
            )
    assert error.value.__cause__.diag.constraint_name == "uq_t12_02"


@pytest.mark.parametrize("missing", ["decided_by", "decided_at", "decision_reason", "empty_reason"])
@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_researcher_request_resolution_requires_reviewer_date_and_reason(
    records, decision, missing
):
    values = decided_values("academics_researcher_request", records, decision)
    values["decision_reason" if missing == "empty_reason" else missing] = (
        "   " if missing == "empty_reason" else None
    )
    assert_rejected("academics_researcher_request", values, "ck_t13_03")


@pytest.mark.parametrize("decision", ["pending", "approved", "rejected"])
def test_request_alone_does_not_create_a_researcher_award(records, decision):
    table = "academics_researcher_request"
    values = (
        valid_values(table, records)
        if decision == "pending"
        else decided_values(table, records, decision)
    )
    identifier = insert_row(table, values)
    assert ResearcherRequest.objects.get(pk=identifier).decision == decision
    assert ResearcherAward.objects.count() == 0


@pytest.mark.parametrize("field", ["account_id", "challenge_id"])
def test_challenge_and_account_cannot_be_mismatched(records, field):
    change = records.other.pk if field == "account_id" else records.other_challenge.pk
    assert_rejected(
        "academics_personal_verification", {**email_values(records), field: change}, "fk_t12_02"
    )


def test_challenge_cannot_change_account_under_a_verification(records):
    insert_row("academics_personal_verification", email_values(records))
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            EmailChallenge.objects.filter(pk=records.challenge.pk).update(account=records.other)
    assert error.value.__cause__.diag.constraint_name == "fk_t12_02"


@pytest.mark.parametrize("dimension", ["account_id", "academic_scope_id"])
def test_award_and_source_request_must_match_person_and_scope(records, dimension):
    values = {
        **valid_values("academics_researcher_award", records),
        "source_request_id": records.request.pk,
    }
    changed = records.other.pk if dimension == "account_id" else records.other_scope.pk
    assert_rejected("academics_researcher_award", {**values, dimension: changed}, "fk_t14_05")


@pytest.mark.parametrize("dimension", ["account_id", "academic_scope_id"])
def test_source_request_cannot_change_person_or_scope_under_an_award(records, dimension):
    insert_row(
        "academics_researcher_award",
        {
            **valid_values("academics_researcher_award", records),
            "source_request_id": records.request.pk,
        },
    )
    changed = records.other.pk if dimension == "account_id" else records.other_scope.pk
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            ResearcherRequest.objects.filter(pk=records.request.pk).update(**{dimension: changed})
    assert error.value.__cause__.diag.constraint_name == "fk_t14_05"


def test_award_can_reference_matching_approved_request_and_join_it(records):
    identifier = insert_row(
        "academics_researcher_award",
        {
            **valid_values("academics_researcher_award", records),
            "source_request_id": records.request.pk,
        },
    )
    award = ResearcherAward.objects.select_related("source_request").get(pk=identifier)
    assert (
        award.source_request == records.request and award.account_id == records.request.account_id
    )
    assert award.academic_scope_id == records.request.academic_scope_id


def test_source_request_is_unique_across_award_history(records):
    values = {
        **valid_values("academics_researcher_award", records),
        "source_request_id": records.request.pk,
        "ended_at": DECIDED,
        "ended_by": records.reviewer.pk,
    }
    insert_row("academics_researcher_award", values)
    assert_rejected("academics_researcher_award", values, "uq_t14_key01")


def test_direct_awards_allow_multiple_null_sources_and_preserve_finished_history(records):
    values = valid_values("academics_researcher_award", records)
    for _ in range(2):
        insert_row(
            "academics_researcher_award",
            {**values, "ended_at": DECIDED, "ended_by": records.reviewer.pk},
        )
    current = insert_row("academics_researcher_award", values)
    assert ResearcherAward.objects.filter(source_request__isnull=True).count() == 3
    assert ResearcherAward.objects.get(pk=current).ended_at is None


def test_only_one_current_award_per_person_and_scope_with_history_preserved(records):
    table = "academics_researcher_award"
    values = valid_values(table, records)
    first = insert_row(table, values)
    assert_rejected(table, values, "uq_t14_01")
    ResearcherAward.objects.filter(pk=first).update(ended_at=DECIDED, ended_by=records.reviewer)
    second = insert_row(table, values)
    assert first != second and ResearcherAward.objects.count() == 2
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            ResearcherAward.objects.filter(pk=first).update(ended_at=None, ended_by=None)
    assert error.value.__cause__.diag.constraint_name == "uq_t14_01"


@pytest.mark.parametrize("dimension", ["account_id", "academic_scope_id"])
def test_current_award_uniqueness_allows_other_people_and_scopes(records, dimension):
    table = "academics_researcher_award"
    values = valid_values(table, records)
    insert_row(table, values)
    changed = records.other.pk if dimension == "account_id" else records.other_scope.pk
    insert_row(table, {**values, dimension: changed})
    assert ResearcherAward.objects.filter(ended_at__isnull=True).count() == 2


def target_values(table, field, records):
    values = valid_values(table, records)
    if field == "challenge_id" or field == "domain_id":
        values = email_values(records)
    elif field == "decided_by":
        values = decided_values(table, records)
    elif field == "ended_by":
        values = {**values, "ended_at": DECIDED}
    elif field == "source_request_id":
        values = {**values, "source_request_id": records.request.pk}
    return values


@pytest.mark.parametrize("table,field,constraint,target", REFERENCES)
def test_nonexistent_foreign_targets_are_rejected(records, table, field, constraint, target):
    assert_rejected(table, {**target_values(table, field, records), field: uuid4()}, constraint)


@pytest.mark.parametrize("table,field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_all_references_prevent_deletion_and_cascade(
    records, table, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records.free_account,
        "identity_email_challenge": records.challenge,
        "academics_domain": records.domain,
        "academics_scope": records.free_scope,
        "academics_researcher_request": records.request,
    }[target_table]
    identifier = insert_row(table, {**target_values(table, field, records), field: target.pk})
    with pytest.raises(RestrictedError if via_orm else IntegrityError) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(target_table)),
                        [target.pk],
                    )
    if not via_orm:
        assert error.value.__cause__.diag.constraint_name == constraint
    assert type(target).objects.filter(pk=target.pk).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE id=%s").format(sql.Identifier(table)),
            [identifier],
        )
        assert cursor.fetchone()[0] == 1


def test_changing_login_email_or_withdrawing_domain_does_not_delete_persisted_backing(records):
    identifier = insert_row(
        "academics_personal_verification",
        {
            **email_values(records),
            "status": "approved",
            "decided_at": DECIDED,
            "decision_reason": "Consumo sintético",
        },
    )
    records.account.email = "otro-correo-sintetico@example.org"
    records.account.save(update_fields=["email"])
    records.domain.status = "withdrawn"
    records.domain.save(update_fields=["status"])
    backing = PersonalVerification.objects.get(pk=identifier)
    assert backing.status == "approved" and backing.domain_id == records.domain.pk
    records.challenge.refresh_from_db()
    assert records.challenge.email_snapshot == "respaldo-persona@example.org"


def test_outer_transaction_rolls_back_request_award_and_personal_backing(records):
    before = {model: model.objects.count() for model in MODELS}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            insert_row(
                "academics_personal_verification",
                valid_values("academics_personal_verification", records),
            )
            request = insert_row(
                "academics_researcher_request",
                decided_values("academics_researcher_request", records),
            )
            insert_row(
                "academics_researcher_award",
                {
                    **valid_values("academics_researcher_award", records),
                    "source_request_id": request,
                },
            )
            raise RuntimeError("fallo sintético de coordinación")
    assert {model: model.objects.count() for model in MODELS} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "case,constraint",
    [
        ("manual", "uq_t12_02"),
        ("challenge", "uq_t12_01"),
        ("award", "uq_t14_01"),
        ("source", "uq_t14_key01"),
    ],
)
def test_concurrent_inserts_obey_pending_challenge_current_award_and_source_uniqueness(
    records, case, constraint
):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    table = (
        "academics_personal_verification"
        if case in ("manual", "challenge")
        else "academics_researcher_award"
    )
    values = email_values(records) if case == "challenge" else valid_values(table, records)
    if case == "source":
        values = {
            **values,
            "source_request_id": records.request.pk,
            "ended_at": DECIDED,
            "ended_by": records.reviewer.pk,
        }
    barrier = Barrier(2)

    def worker(_):
        try:
            assert connection.settings_dict["NAME"] == "test_entrepares"
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout='5s'")
                    cursor.execute("SET LOCAL statement_timeout='10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=5)
                identifier = insert_row(table, values)
            return "created", str(identifier), pid
        except IntegrityError as error:
            return "rejected", error.__cause__.diag.constraint_name, pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2), timeout=20))
    assert sorted(result[0] for result in results) == ["created", "rejected"]
    assert len({result[2] for result in results}) == 2
    assert next(result[1] for result in results if result[0] == "rejected") == constraint
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_backing_migration_reverses_and_restores_complete_graph_preserving_existing_data():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-respaldo@example.org")
    institution = Institution.objects.create(
        name="Institución sintética conservada", kind="other", origin="declared"
    )
    scope = AcademicScope.objects.create(
        institution=institution, name="Ámbito sintético conservado", kind="other"
    )
    challenge = EmailChallenge.objects.create(
        account=account,
        purpose="email_confirmation",
        email_snapshot=account.email,
        created_at=CREATED,
        expires_at=CREATED + timedelta(days=1),
    )
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("academics", "0001_catalogs_and_scopes")])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert (
            Account.objects.filter(pk=account.pk).exists()
            and EmailChallenge.objects.filter(pk=challenge.pk).exists()
        )
        assert AcademicScope.objects.filter(pk=scope.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables
    assert not MigrationExecutor(connection).migration_plan(targets)
    test_fourteen_named_restrict_foreign_keys_include_exact_composite_keys()
    test_unique_predicates_and_nulls_distinct_allow_direct_awards()
    assert (
        Account.objects.filter(pk=account.pk).exists()
        and EmailChallenge.objects.filter(pk=challenge.pk).exists()
    )
    assert AcademicScope.objects.filter(pk=scope.pk).exists()
