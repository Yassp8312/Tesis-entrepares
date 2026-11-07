"""T26–T31: integridad, revisión propia y conservación con datos sintéticos."""

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

from modules.access.models import Capability
from modules.identity.models import Account
from modules.moderation.models import (
    Decision,
    Measure,
    Report,
    Restriction,
    ReviewDecision,
    ReviewRequest,
)
from modules.opportunities.models import Opportunity
from modules.publications.models import Publication

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=1)
SCHEMA = {
    "moderation_report": {
        "id": ("uuid", False),
        "opportunity_id": ("uuid", True),
        "publication_id": ("uuid", True),
        "reported_by": ("uuid", False),
        "reason": ("text", False),
        "created_at": ("timestamp with time zone", False),
    },
    "moderation_decision": {
        "id": ("uuid", False),
        "report_id": ("uuid", False),
        "decided_by": ("uuid", False),
        "outcome": ("character varying(16)", False),
        "reason": ("text", False),
        "content_action": ("character varying(16)", False),
        "created_at": ("timestamp with time zone", False),
    },
    "moderation_measure": {
        "id": ("uuid", False),
        "account_id": ("uuid", False),
        "source_decision_id": ("uuid", False),
        "kind": ("character varying(16)", False),
        "starts_at": ("timestamp with time zone", False),
        "ends_at": ("timestamp with time zone", True),
        "note": ("text", True),
        "revoked_at": ("timestamp with time zone", True),
        "revoked_by": ("uuid", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "moderation_restriction": {
        "id": ("uuid", False),
        "measure_id": ("uuid", False),
        "capability_code": ("character varying(80)", False),
        "context_kind": ("character varying(16)", False),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "moderation_review_request": {
        "id": ("uuid", False),
        "measure_id": ("uuid", False),
        "requested_by": ("uuid", False),
        "reason": ("text", False),
        "created_at": ("timestamp with time zone", False),
    },
    "moderation_review_decision": {
        "id": ("uuid", False),
        "request_id": ("uuid", False),
        "decided_by": ("uuid", False),
        "outcome": ("character varying(16)", False),
        "reason": ("text", False),
        "replacement_measure_id": ("uuid", True),
        "created_at": ("timestamp with time zone", False),
    },
}
REFERENCES = [
    ("moderation_report", ("opportunity_id",), "fk_t26_01", "opportunities_opportunity", ("id",)),
    ("moderation_report", ("publication_id",), "fk_t26_02", "publications_publication", ("id",)),
    ("moderation_report", ("reported_by",), "fk_t26_03", "identity_account", ("id",)),
    ("moderation_decision", ("report_id",), "fk_t27_01", "moderation_report", ("id",)),
    ("moderation_decision", ("decided_by",), "fk_t27_02", "identity_account", ("id",)),
    ("moderation_measure", ("account_id",), "fk_t28_01", "identity_account", ("id",)),
    ("moderation_measure", ("source_decision_id",), "fk_t28_02", "moderation_decision", ("id",)),
    ("moderation_measure", ("revoked_by",), "fk_t28_03", "identity_account", ("id",)),
    ("moderation_restriction", ("measure_id",), "fk_t29_01", "moderation_measure", ("id",)),
    ("moderation_restriction", ("capability_code",), "fk_t29_02", "access_capability", ("code",)),
    (
        "moderation_review_request",
        ("measure_id", "requested_by"),
        "fk_t30_01",
        "moderation_measure",
        ("id", "account_id"),
    ),
    (
        "moderation_review_decision",
        ("request_id",),
        "fk_t31_01",
        "moderation_review_request",
        ("id",),
    ),
    ("moderation_review_decision", ("decided_by",), "fk_t31_02", "identity_account", ("id",)),
    (
        "moderation_review_decision",
        ("replacement_measure_id",),
        "fk_t31_03",
        "moderation_measure",
        ("id",),
    ),
]
MODELS = {
    "moderation_report": Report,
    "moderation_decision": Decision,
    "moderation_measure": Measure,
    "moderation_restriction": Restriction,
    "moderation_review_request": ReviewRequest,
    "moderation_review_decision": ReviewDecision,
}


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


def report_values(records, target="opportunity"):
    return {
        target + "_id": records.opportunity.pk
        if target == "opportunity"
        else records.publication.pk,
        "reported_by": records.actor.pk,
        "reason": "Reporte sintético motivado",
    }


def decision_values(records):
    return {
        "report_id": records.report.pk,
        "decided_by": records.actor.pk,
        "outcome": "violation",
        "reason": "Decisión sintética motivada",
        "content_action": "hide",
    }


def measure_values(records):
    return {
        "account_id": records.affected.pk,
        "source_decision_id": records.decision.pk,
        "kind": "ban",
    }


def restriction_values(records):
    return {
        "measure_id": records.measure.pk,
        "capability_code": records.capability.pk,
        "context_kind": "personal",
    }


def request_values(records):
    return {
        "measure_id": records.measure.pk,
        "requested_by": records.affected.pk,
        "reason": "Solicitud sintética motivada",
    }


def review_values(records):
    return {
        "request_id": records.request.pk,
        "decided_by": records.actor.pk,
        "outcome": "upheld",
        "reason": "Resolución sintética motivada",
    }


def values_for_table(records, table):
    return {
        "moderation_report": report_values,
        "moderation_decision": decision_values,
        "moderation_measure": measure_values,
        "moderation_restriction": restriction_values,
        "moderation_review_request": request_values,
        "moderation_review_decision": review_values,
    }[table](records)


def new_report(records):
    return Report.objects.create(
        opportunity=records.opportunity,
        reported_by=records.actor,
        reason="Reporte sintético independiente",
    )


def new_decision(records):
    return Decision.objects.create(
        report=new_report(records),
        decided_by=records.actor,
        outcome="violation",
        reason="Decisión sintética independiente",
        content_action="none",
    )


def new_measure(records, account=None):
    return Measure.objects.create(
        account=account or records.affected,
        source_decision=records.decision,
        kind="ban",
        starts_at=START,
    )


@pytest.fixture
def records():
    actor, affected, other, free = [
        Account.objects.create_user(f"moderacion-{name}@example.org")
        for name in ("actor", "afectado", "otro", "libre")
    ]
    capability = Capability.objects.create(
        code="synthetic.publish", description="Capacidad sintética restringible"
    )
    free_capability = Capability.objects.create(
        code="synthetic.free", description="Capacidad sintética independiente"
    )
    Capability.objects.create(
        code="moderation.request_review", description="Vía sintética de revisión protegida"
    )
    opportunity = Opportunity.objects.create(
        owner_account=actor,
        author=actor,
        title="Oportunidad sintética",
        description="Necesidad sintética",
        area="Área sintética",
        responsible_label="Responsable sintético",
    )
    publication = Publication.objects.create(
        owner_account=actor,
        author=actor,
        kind="news",
        title="Publicación sintética",
        body="Contenido sintético",
    )
    r = SimpleNamespace(
        actor=actor,
        affected=affected,
        other=other,
        free=free,
        capability=capability,
        free_capability=free_capability,
        opportunity=opportunity,
        publication=publication,
    )
    r.report = new_report(r)
    r.decision = Decision.objects.create(
        report=r.report,
        decided_by=actor,
        outcome="violation",
        reason="Motivo sintético original",
        content_action="none",
    )
    r.measure = new_measure(r)
    r.request = ReviewRequest.objects.create(
        measure=r.measure, requested_by=affected, reason="Solicitud sintética inicial"
    )
    return r


@pytest.mark.parametrize(
    "table,number,count",
    [
        ("moderation_report", 26, 2),
        ("moderation_decision", 27, 4),
        ("moderation_measure", 28, 4),
        ("moderation_restriction", 29, 2),
        ("moderation_review_request", 30, 1),
        ("moderation_review_decision", 31, 3),
    ],
)
def test_forty_two_columns_and_sixteen_checks_match_design(table, number, count):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",
            [table],
        )
        assert {name: (kind, nullable) for name, kind, nullable in cursor} == SCHEMA[table]
        constraints = connection.introspection.get_constraints(cursor, table)
    assert {name for name, value in constraints.items() if value["check"]} == {
        f"ck_t{number:02}_{n:02}" for n in range(1, count + 1)
    }


def test_fourteen_named_restrict_references_include_compound_ownership():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid=ANY(%s::regclass[]) AND contype='f'",
            [list(SCHEMA)],
        )
        rows = cursor.fetchall()
    assert {name: definition for name, definition, *_ in rows} == {
        name: f"FOREIGN KEY ({', '.join(fields)}) REFERENCES {target}({', '.join(keys)}) ON DELETE RESTRICT"
        for _, fields, name, target, keys in REFERENCES
    }
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )
    assert not ReviewRequest._meta.get_field("measure").db_constraint
    assert not ReviewRequest._meta.get_field("requested_by").db_constraint


def test_ten_indexes_and_five_unique_keys_preserve_reference_columns():
    ordinary = (
        {f"ix_t26_{n:02}" for n in range(1, 4)}
        | {"ix_t27_01"}
        | {f"ix_t28_{n:02}" for n in range(1, 4)}
        | {"ix_t29_01", "ix_t30_01", "ix_t31_01"}
    )
    unique = {"uq_t27_key01", "uq_t28_key01", "uq_t29_key01", "uq_t31_key01", "uq_t31_key02"}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,pg_get_indexdef(i.indexrelid),i.indisunique,pg_get_expr(i.indpred,i.indrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=ANY(%s::regclass[]) AND NOT i.indisprimary",
            [list(SCHEMA)],
        )
        indexes = {
            name: (definition, unique, predicate) for name, definition, unique, predicate in cursor
        }
        constraints = {
            table: connection.introspection.get_constraints(cursor, table) for table in SCHEMA
        }
    assert set(indexes) == ordinary | unique
    assert {name for name, (_, is_unique, _) in indexes.items() if is_unique} == unique
    assert all(predicate is None for _, _, predicate in indexes.values())
    assert "account_id, starts_at" in indexes["ix_t28_01"][0]
    assert "measure_id, requested_by" in indexes["ix_t30_01"][0]
    for table, key, columns in [
        ("moderation_decision", "uq_t27_key01", ["report_id"]),
        ("moderation_measure", "uq_t28_key01", ["id", "account_id"]),
        (
            "moderation_restriction",
            "uq_t29_key01",
            ["measure_id", "capability_code", "context_kind"],
        ),
        ("moderation_review_decision", "uq_t31_key01", ["request_id"]),
        ("moderation_review_decision", "uq_t31_key02", ["replacement_measure_id"]),
    ]:
        assert constraints[table][key]["columns"] == columns


@pytest.mark.parametrize("target", ["opportunity", "publication"])
def test_reporting_does_not_automatically_change_content_or_identity(records, target):
    identifier = insert_row("moderation_report", report_values(records, target))
    assert not Decision.objects.filter(report_id=identifier).exists()
    row = records.opportunity if target == "opportunity" else records.publication
    row.refresh_from_db()
    records.actor.refresh_from_db()
    assert row.visibility == "visible" and records.actor.is_active


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("moderation_report", {"opportunity_id": None}, "ck_t26_01"),
        ("moderation_report", {"publication_id": "publication"}, "ck_t26_01"),
        ("moderation_report", {"reason": ""}, "ck_t26_02"),
        ("moderation_report", {"reason": "   "}, "ck_t26_02"),
        ("moderation_decision", {"outcome": "invalid"}, "ck_t27_01"),
        ("moderation_decision", {"content_action": "invalid"}, "ck_t27_02"),
        ("moderation_decision", {"reason": ""}, "ck_t27_03"),
        ("moderation_decision", {"reason": "   "}, "ck_t27_03"),
        ("moderation_decision", {"outcome": "no_violation", "content_action": "hide"}, "ck_t27_04"),
        (
            "moderation_decision",
            {"outcome": "no_violation", "content_action": "remove"},
            "ck_t27_04",
        ),
        ("moderation_measure", {"kind": "invalid"}, "ck_t28_01"),
        ("moderation_measure", {"starts_at": START, "ends_at": START}, "ck_t28_02"),
        ("moderation_measure", {"starts_at": END, "ends_at": START}, "ck_t28_02"),
        ("moderation_measure", {"revoked_at": END}, "ck_t28_03"),
        ("moderation_measure", {"revoked_by": "actor"}, "ck_t28_03"),
        (
            "moderation_measure",
            {"kind": "warning", "starts_at": START, "ends_at": END},
            "ck_t28_04",
        ),
        ("moderation_restriction", {"context_kind": "invalid"}, "ck_t29_01"),
        ("moderation_restriction", {"capability_code": "moderation.request_review"}, "ck_t29_02"),
        ("moderation_review_request", {"reason": ""}, "ck_t30_01"),
        ("moderation_review_request", {"reason": "   "}, "ck_t30_01"),
        ("moderation_review_decision", {"outcome": "invalid"}, "ck_t31_01"),
        ("moderation_review_decision", {"reason": ""}, "ck_t31_02"),
        ("moderation_review_decision", {"reason": "   "}, "ck_t31_02"),
        ("moderation_review_decision", {"outcome": "replaced"}, "ck_t31_03"),
        ("moderation_review_decision", {"replacement_measure_id": "measure"}, "ck_t31_03"),
    ],
)
def test_check_constraints_reject_incompatible_direct_sql(records, table, changes, constraint):
    changes = {
        key: getattr(records, value).pk
        if key in ("publication_id", "revoked_by", "replacement_measure_id")
        and isinstance(value, str)
        else value
        for key, value in changes.items()
    }
    values = values_for_table(records, table)
    if table == "moderation_decision":
        values["report_id"] = new_report(records).pk
    assert_rejected(table, {**values, **changes}, constraint)


@pytest.mark.parametrize(
    "outcome,action",
    [
        ("violation", "none"),
        ("violation", "hide"),
        ("violation", "remove"),
        ("no_violation", "none"),
    ],
)
def test_each_valid_initial_outcome_and_action_can_be_recorded(records, outcome, action):
    identifier = insert_row(
        "moderation_decision",
        {
            **decision_values(records),
            "report_id": new_report(records).pk,
            "outcome": outcome,
            "content_action": action,
        },
    )
    assert Decision.objects.get(pk=identifier).content_action == action


@pytest.mark.parametrize("kind,ends_at", [("warning", None), ("ban", None), ("ban", END)])
def test_measure_preserves_kind_duration_and_identity_enablement(records, kind, ends_at):
    identifier = insert_row(
        "moderation_measure",
        {**measure_values(records), "kind": kind, "starts_at": START, "ends_at": ends_at},
    )
    row = Measure.objects.get(pk=identifier)
    records.affected.refresh_from_db()
    assert row.ends_at == ends_at and row.kind == kind and records.affected.is_active


@pytest.mark.parametrize("context", ["personal", "organization", "both"])
def test_restriction_contexts_and_uniqueness_are_stored_without_scope_inference(records, context):
    values = {**restriction_values(records), "context_kind": context}
    insert_row("moderation_restriction", values)
    assert_rejected("moderation_restriction", values, "uq_t29_key01")
    insert_row("moderation_restriction", {**values, "capability_code": records.free_capability.pk})
    assert Restriction.objects.count() == 2


def test_compound_review_reference_rejects_other_requester_and_parent_change(records):
    assert_rejected(
        "moderation_review_request",
        {**request_values(records), "requested_by": records.other.pk},
        "fk_t30_01",
    )
    for model, identifier, changes in [
        (ReviewRequest, records.request.pk, {"requested_by_id": records.other.pk}),
        (Measure, records.measure.pk, {"account_id": records.other.pk}),
    ]:
        with pytest.raises(IntegrityError) as error:
            with transaction.atomic():
                model.objects.filter(pk=identifier).update(**changes)
        assert error.value.__cause__.diag.constraint_name == "fk_t30_01"
    records.request.refresh_from_db()
    records.measure.refresh_from_db()
    assert records.request.requested_by_id == records.measure.account_id == records.affected.pk


def test_review_cannot_move_to_another_person_measure_but_accepts_same_person(records):
    other = new_measure(records, records.other)
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            ReviewRequest.objects.filter(pk=records.request.pk).update(measure=other)
    assert error.value.__cause__.diag.constraint_name == "fk_t30_01"
    same = new_measure(records)
    ReviewRequest.objects.filter(pk=records.request.pk).update(measure=same)
    assert ReviewRequest.objects.get(pk=records.request.pk).measure_id == same.pk


def test_multiple_review_requests_and_null_replacements_preserve_history(records):
    second = insert_row("moderation_review_request", request_values(records))
    insert_row("moderation_review_decision", review_values(records))
    insert_row(
        "moderation_review_decision",
        {**review_values(records), "request_id": second, "outcome": "revoked"},
    )
    assert ReviewRequest.objects.filter(measure=records.measure).count() == 2
    assert ReviewDecision.objects.filter(replacement_measure__isnull=True).count() == 2


def test_each_report_and_review_request_has_only_one_decision(records):
    assert_rejected("moderation_decision", decision_values(records), "uq_t27_key01")
    insert_row("moderation_review_decision", review_values(records))
    assert_rejected("moderation_review_decision", review_values(records), "uq_t31_key01")


def test_replacement_is_unique_and_keeps_original_decision_and_revoked_measure(records):
    original_reason = records.decision.reason
    replacement = new_measure(records)
    with transaction.atomic():
        Measure.objects.filter(pk=records.measure.pk).update(
            revoked_at=END, revoked_by=records.actor
        )
        insert_row(
            "moderation_review_decision",
            {
                **review_values(records),
                "outcome": "replaced",
                "replacement_measure_id": replacement.pk,
            },
        )
    other_request = insert_row("moderation_review_request", request_values(records))
    assert_rejected(
        "moderation_review_decision",
        {
            **review_values(records),
            "request_id": other_request,
            "outcome": "replaced",
            "replacement_measure_id": replacement.pk,
        },
        "uq_t31_key02",
    )
    records.measure.refresh_from_db()
    records.decision.refresh_from_db()
    assert records.measure.revoked_at == END and records.decision.reason == original_reason
    assert Measure.objects.filter(pk=replacement.pk).exists()


@pytest.mark.parametrize("table", SCHEMA)
def test_sql_defaults_and_uuid_only_representation(records, table):
    values = values_for_table(records, table)
    if table == "moderation_decision":
        values["report_id"] = new_report(records).pk
    identifier = insert_row(table, values)
    row = MODELS[table].objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(row) == str(identifier)
    assert row.created_at.utcoffset().total_seconds() == 0
    if hasattr(row, "updated_at"):
        assert row.updated_at == row.created_at
    if table == "moderation_measure":
        assert row.starts_at == row.created_at and row.ends_at is None and row.revoked_at is None


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("moderation_measure", "note", "Nota sintética editada"),
        ("moderation_restriction", "context_kind", "both"),
    ],
)
def test_partial_save_preserves_creation_and_updates_timestamp(records, table, field, value):
    identifier = insert_row(
        table, {**values_for_table(records, table), "created_at": START, "updated_at": START}
    )
    row = MODELS[table].objects.get(pk=identifier)
    setattr(row, field, value)
    row.save(update_fields={field})
    row.refresh_from_db()
    assert row.created_at == START and row.updated_at > START and getattr(row, field) == value


def values_for_reference(records, table, fields, target_id):
    values = values_for_table(records, table)
    field = fields[0]
    if table == "moderation_report" and field == "publication_id":
        values.pop("opportunity_id")
    if table == "moderation_decision":
        values["report_id"] = new_report(records).pk
    if field == "revoked_by":
        values["revoked_at"] = END
    if field == "replacement_measure_id":
        values["outcome"] = "replaced"
    values[field] = target_id
    return values


@pytest.mark.parametrize("table,fields,constraint,target,keys", REFERENCES)
def test_missing_references_are_rejected(records, table, fields, constraint, target, keys):
    missing = "synthetic.missing" if target == "access_capability" else uuid4()
    assert_rejected(table, values_for_reference(records, table, fields, missing), constraint)


@pytest.mark.parametrize("table,fields,constraint,target_table,keys", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_all_fourteen_references_restrict_sql_and_orm_deletion(
    records, table, fields, constraint, target_table, keys, via_orm
):
    if target_table == "moderation_report":
        target = new_report(records)
    elif target_table == "moderation_decision":
        target = new_decision(records)
    elif target_table == "moderation_measure":
        target = new_measure(records)
    elif target_table == "moderation_review_request":
        target = ReviewRequest.objects.create(
            measure=records.measure,
            requested_by=records.affected,
            reason="Petición sintética independiente",
        )
    else:
        target = {
            "identity_account": records.free,
            "opportunities_opportunity": records.opportunity,
            "publications_publication": records.publication,
            "access_capability": records.free_capability,
        }[target_table]
    values = values_for_reference(records, table, fields, target.pk)
    if table == "moderation_review_request":
        values["requested_by"] = target.account_id
    identifier = insert_row(table, values)
    with pytest.raises(RestrictedError if via_orm else IntegrityError) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE {}=%s").format(
                            sql.Identifier(target_table),
                            sql.Identifier("code" if target_table == "access_capability" else "id"),
                        ),
                        [target.pk],
                    )
    if not via_orm:
        assert error.value.__cause__.diag.constraint_name == constraint
    assert (
        type(target).objects.filter(pk=target.pk).exists()
        and MODELS[table].objects.filter(pk=identifier).exists()
    )


def test_outer_failure_rolls_back_report_decision_measure_restrictions_and_review(records):
    before = {table: model.objects.count() for table, model in MODELS.items()}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            report = insert_row("moderation_report", report_values(records))
            decision = insert_row(
                "moderation_decision", {**decision_values(records), "report_id": report}
            )
            measure = insert_row(
                "moderation_measure", {**measure_values(records), "source_decision_id": decision}
            )
            insert_row(
                "moderation_restriction", {**restriction_values(records), "measure_id": measure}
            )
            request = insert_row(
                "moderation_review_request", {**request_values(records), "measure_id": measure}
            )
            insert_row(
                "moderation_review_decision", {**review_values(records), "request_id": request}
            )
            raise RuntimeError("fallo sintético de coordinación")
    assert {table: model.objects.count() for table, model in MODELS.items()} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "scenario,constraint",
    [
        ("decision", "uq_t27_key01"),
        ("restriction", "uq_t29_key01"),
        ("review", "uq_t31_key01"),
        ("replacement", "uq_t31_key02"),
    ],
)
def test_concurrent_decisions_restrictions_and_replacements_do_not_duplicate(
    records, scenario, constraint
):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    table = {
        "decision": "moderation_decision",
        "restriction": "moderation_restriction",
        "review": "moderation_review_decision",
        "replacement": "moderation_review_decision",
    }[scenario]
    values = [values_for_table(records, table) for _ in range(2)]
    if scenario == "decision":
        report = new_report(records)
        for value in values:
            value["report_id"] = report.pk
    if scenario == "replacement":
        values[1]["request_id"] = insert_row("moderation_review_request", request_values(records))
        replacement = new_measure(records)
        for value in values:
            value.update(outcome="replaced", replacement_measure_id=replacement.pk)
    barrier = Barrier(2)

    def worker(index):
        try:
            assert connection.settings_dict["NAME"] == "test_entrepares"
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout='5s'")
                    cursor.execute("SET LOCAL statement_timeout='10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=5)
                identifier = insert_row(table, values[index])
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


@pytest.mark.django_db(transaction=True)
def test_migration_reverses_and_restores_composite_review_reference(records):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("moderation", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert (
            Account.objects.filter(pk=records.affected.pk).exists()
            and Capability.objects.filter(pk=records.capability.pk).exists()
        )
        assert (
            Opportunity.objects.filter(pk=records.opportunity.pk).exists()
            and Publication.objects.filter(pk=records.publication.pk).exists()
        )
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables and not MigrationExecutor(
        connection
    ).migration_plan(targets)
    test_fourteen_named_restrict_references_include_compound_ownership()
    test_ten_indexes_and_five_unique_keys_preserve_reference_columns()
