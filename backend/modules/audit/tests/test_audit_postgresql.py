"""T37 real: integridad SQL y escritura mínima propietaria, sin consulta pública."""

from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql
from psycopg.types.json import Jsonb

from core.clock import FixedClock
from core.correlation import OperationContext
from modules.academics.models import AcademicScope, Institution
from modules.audit.commands import append_event
from modules.audit.contracts import (
    ActorKind,
    AuditEntry,
    AuditProjection,
    AuditReason,
    AuditState,
    ContextKind,
)
from modules.audit.models import AuditEvent
from modules.identity.models import Account
from modules.organizations.models import Organization

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
INSTANT = datetime(2026, 1, 1, tzinfo=UTC)
SCHEMA = {
    "id": ("uuid", False),
    "actor_kind": ("character varying(16)", False),
    "actor_account_id": ("uuid", True),
    "context_kind": ("character varying(16)", False),
    "organization_id": ("uuid", True),
    "academic_scope_id": ("uuid", True),
    "action_code": ("character varying(80)", False),
    "resource_kind": ("character varying(80)", False),
    "resource_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "reason": ("text", True),
    "before_state": ("jsonb", True),
    "after_state": ("jsonb", True),
    "correlation_id": ("uuid", False),
}
REFERENCES = [
    ("actor_account_id", "fk_t37_01", "identity_account"),
    ("organization_id", "fk_t37_02", "organizations_organization"),
    ("academic_scope_id", "fk_t37_03", "academics_scope"),
]


def insert_row(values):
    values = {
        key: value
        if isinstance(value, Jsonb)
        else Jsonb(value)
        if key in ("before_state", "after_state") and value is not None
        else value
        for key, value in values.items()
    }
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO audit_event ({}) VALUES ({}) RETURNING id").format(
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.Placeholder() for _ in values),
            ),
            list(values.values()),
        )
        return cursor.fetchone()[0]


def assert_rejected(values, constraint):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            insert_row(values)
    assert error.value.__cause__.diag.constraint_name == constraint


def system_values():
    return {
        "actor_kind": "system",
        "context_kind": "system",
        "action_code": "synthetic.created",
        "resource_kind": "synthetic.record",
        "resource_id": uuid4(),
        "correlation_id": uuid4(),
    }


@pytest.fixture
def records():
    actor = Account.objects.create_user("actor-auditoria@example.org")
    owner = Account.objects.create_user("titular-entidad-auditoria@example.org")
    institution = Institution.objects.create(
        name="Institución sintética de auditoría", kind="other", origin="declared"
    )
    scope = AcademicScope.objects.create(
        institution=institution, name="Ámbito sintético de auditoría", kind="other"
    )
    organization = Organization.objects.create(
        name="Entidad sintética de auditoría", kind="other", created_by=owner
    )
    return SimpleNamespace(
        actor=actor, owner=owner, institution=institution, scope=scope, organization=organization
    )


def account_values(records, *, organizational=False):
    values = {
        **system_values(),
        "actor_kind": "account",
        "actor_account_id": records.actor.pk,
        "context_kind": "organization" if organizational else "personal",
    }
    if organizational:
        values["organization_id"] = records.organization.pk
    return values


def test_schema_matches_fourteen_columns_eight_checks_and_five_indexes():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull FROM pg_attribute WHERE attrelid='audit_event'::regclass AND attnum>0 AND NOT attisdropped"
        )
        assert {name: (kind, nullable) for name, kind, nullable in cursor} == SCHEMA
        constraints = connection.introspection.get_constraints(cursor, "audit_event")
    assert {key for key, value in constraints.items() if value["check"]} == {
        f"ck_t37_{n:02}" for n in range(1, 9)
    }
    assert {key: value["columns"] for key, value in constraints.items() if value["index"]} == {
        "ix_t37_01": ["resource_kind", "resource_id", "occurred_at"],
        "ix_t37_02": ["actor_account_id", "occurred_at"],
        "ix_t37_03": ["correlation_id"],
        "ix_t37_04": ["organization_id"],
        "ix_t37_05": ["academic_scope_id"],
    }
    assert not any(value["unique"] and not value["primary_key"] for value in constraints.values())


def test_only_three_context_foreign_keys_exist_and_use_restrict():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid='audit_event'::regclass AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: definition for name, definition, *_ in rows} == {
        name: f"FOREIGN KEY ({field}) REFERENCES {target}(id) ON DELETE RESTRICT"
        for field, name, target in REFERENCES
    }
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


def test_sql_defaults_and_historical_resource_reference_work_without_operational_resource():
    values = system_values()
    identifier = insert_row(values)
    event = AuditEvent.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(event) == str(identifier)
    assert (
        event.resource_id == values["resource_id"]
        and event.correlation_id == values["correlation_id"]
    )
    assert event.occurred_at.utcoffset().total_seconds() == 0
    assert event.reason is None and event.before_state is None and event.after_state is None
    assert event.actor_account_id is None and event.organization_id is None


@pytest.mark.parametrize("kind", ["system", "personal", "organization"])
def test_valid_actor_context_combinations(records, kind):
    values = (
        system_values()
        if kind == "system"
        else account_values(records, organizational=kind == "organization")
    )
    identifier = insert_row({**values, "academic_scope_id": records.scope.pk})
    event = AuditEvent.objects.get(pk=identifier)
    assert event.context_kind == kind and event.academic_scope_id == records.scope.pk


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"actor_kind": "invalid"}, "ck_t37_01"),
        ({"context_kind": "invalid"}, "ck_t37_02"),
        ({"action_code": ""}, "ck_t37_03"),
        ({"action_code": "   "}, "ck_t37_03"),
        ({"resource_kind": ""}, "ck_t37_04"),
        ({"resource_kind": "   "}, "ck_t37_04"),
        ({"actor_account_id": "actor"}, "ck_t37_05"),
        ({"context_kind": "personal"}, "ck_t37_05"),
        ({"actor_kind": "account", "context_kind": "personal"}, "ck_t37_05"),
        ({"actor_kind": "account", "actor_account_id": "actor"}, "ck_t37_05"),
        (
            {"actor_kind": "account", "actor_account_id": "actor", "context_kind": "organization"},
            "ck_t37_06",
        ),
        ({"organization_id": "organization"}, "ck_t37_06"),
    ],
)
def test_actor_context_and_text_checks_reject_direct_sql(records, changes, constraint):
    changes = {
        key: getattr(records, value).pk
        if key in ("actor_account_id", "organization_id")
        and isinstance(value, str)
        and value in ("actor", "organization")
        else value
        for key, value in changes.items()
    }
    assert_rejected({**system_values(), **changes}, constraint)


@pytest.mark.parametrize(
    "field,constraint", [("before_state", "ck_t37_07"), ("after_state", "ck_t37_08")]
)
@pytest.mark.parametrize("value", [[], False, "texto-sintetico", 42, Jsonb(None)])
def test_json_checks_require_object_or_sql_null(field, constraint, value):
    assert_rejected({**system_values(), field: value}, constraint)


def test_sql_null_and_empty_objects_are_distinct_valid_snapshots():
    first = insert_row({**system_values(), "before_state": None, "after_state": {}})
    second = insert_row(
        {**system_values(), "before_state": {"status": "pending"}, "after_state": None}
    )
    assert AuditEvent.objects.get(pk=first).before_state is None
    assert AuditEvent.objects.get(pk=first).after_state == {}
    assert AuditEvent.objects.get(pk=second).before_state == {"status": "pending"}


def values_for_reference(records, field):
    return (
        account_values(records, organizational=True)
        if field == "organization_id"
        else account_values(records)
    )


@pytest.mark.parametrize("field,constraint,target", REFERENCES)
def test_missing_context_references_are_rejected(records, field, constraint, target):
    assert_rejected({**values_for_reference(records, field), field: uuid4()}, constraint)


@pytest.mark.parametrize("field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_context_references_prevent_deletion_and_cascade(
    records, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records.actor,
        "organizations_organization": records.organization,
        "academics_scope": records.scope,
    }[target_table]
    identifier = insert_row({**values_for_reference(records, field), field: target.pk})
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
    assert (
        type(target).objects.filter(pk=target.pk).exists()
        and AuditEvent.objects.filter(pk=identifier).exists()
    )


def test_owner_writer_persists_only_explicit_projection_and_injected_operation_context(records):
    correlation = uuid4()
    operation = OperationContext(correlation_id=correlation, clock=FixedClock(INSTANT))
    resource = uuid4()
    entry = AuditEntry(
        actor_kind=ActorKind.ACCOUNT,
        actor_account_id=records.actor.pk,
        context_kind=ContextKind.ORGANIZATION,
        organization_id=records.organization.pk,
        academic_scope_id=records.scope.pk,
        action_code="synthetic.review.approved",
        resource_kind="synthetic.request",
        resource_id=resource,
        reason=AuditReason.APPROVED,
        before_state=AuditProjection(status=AuditState.PENDING),
        after_state=AuditProjection(
            status=AuditState.APPROVED, related_resource_id=resource, revision=1
        ),
    )
    receipt = append_event(entry=entry, operation=operation)
    event = AuditEvent.objects.get(pk=receipt.event_id)
    assert (
        event.occurred_at == receipt.occurred_at == INSTANT
        and event.correlation_id == receipt.correlation_id == correlation
    )
    assert (
        event.actor_account_id == records.actor.pk
        and event.organization_id == records.organization.pk
    )
    assert event.reason == "review_approved" and event.before_state == {"status": "pending"}
    assert event.after_state == {
        "status": "approved",
        "related_resource_id": str(resource),
        "revision": 1,
    }
    assert set(asdict(receipt)) == {"event_id", "correlation_id", "occurred_at"}
    with pytest.raises(FrozenInstanceError):
        receipt.event_id = uuid4()


def test_multiple_events_can_share_operation_and_resource_without_overwriting():
    operation = OperationContext.start(clock=FixedClock(INSTANT))
    resource = uuid4()
    entry = AuditEntry(
        actor_kind=ActorKind.SYSTEM,
        context_kind=ContextKind.SYSTEM,
        action_code="synthetic.created",
        resource_kind="synthetic.record",
        resource_id=resource,
    )
    first = append_event(entry=entry, operation=operation)
    second = append_event(entry=entry, operation=operation)
    assert first.event_id != second.event_id
    assert (
        AuditEvent.objects.filter(
            correlation_id=operation.correlation_id, resource_id=resource
        ).count()
        == 2
    )


@pytest.mark.parametrize(
    "field,payload",
    [
        ("reason", "clave-sintetica-no-real"),
        ("reason", "https://example.org/?token=firma-sintetica"),
        ("before_state", {"document": "relato-sintetico-privado"}),
        ("after_state", {"nested": {"contacts": ["privado@example.org"]}}),
    ],
)
def test_rejected_private_payloads_never_reach_audit_storage(field, payload):
    operation = OperationContext.start(clock=FixedClock(INSTANT))
    before = AuditEvent.objects.count()
    with pytest.raises(TypeError):
        entry = AuditEntry(
            actor_kind=ActorKind.SYSTEM,
            context_kind=ContextKind.SYSTEM,
            action_code="synthetic.created",
            resource_kind="synthetic.record",
            resource_id=uuid4(),
            **{field: payload},
        )
        append_event(entry=entry, operation=operation)
    assert AuditEvent.objects.count() == before


def test_outer_transaction_rolls_back_business_change_and_required_event(records):
    operation = OperationContext.start(clock=FixedClock(INSTANT))
    entry = AuditEntry(
        actor_kind=ActorKind.ACCOUNT,
        actor_account_id=records.actor.pk,
        context_kind=ContextKind.PERSONAL,
        action_code="synthetic.updated",
        resource_kind="identity.account",
        resource_id=records.actor.pk,
        reason=AuditReason.UPDATED,
    )
    old_email = records.actor.email
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            Account.objects.filter(pk=records.actor.pk).update(email="cambio-sintetico@example.org")
            append_event(entry=entry, operation=operation)
            raise RuntimeError("fallo sintético de coordinación")
    records.actor.refresh_from_db()
    assert records.actor.email == old_email and AuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_audit_migration_reverses_and_restores_graph_preserving_context_records():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-auditoria@example.org")
    institution = Institution.objects.create(
        name="Institución sintética conservada", kind="other", origin="declared"
    )
    scope = AcademicScope.objects.create(
        institution=institution, name="Ámbito sintético conservado", kind="other"
    )
    organization = Organization.objects.create(
        name="Entidad sintética conservada", kind="other", created_by=account
    )
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("audit", None)])
        assert "audit_event" not in connection.introspection.table_names()
        assert (
            Account.objects.filter(pk=account.pk).exists()
            and AcademicScope.objects.filter(pk=scope.pk).exists()
        )
        assert Organization.objects.filter(pk=organization.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables and not MigrationExecutor(
        connection
    ).migration_plan(targets)
    test_only_three_context_foreign_keys_exist_and_use_restrict()
    assert (
        Account.objects.filter(pk=account.pk).exists()
        and Organization.objects.filter(pk=organization.pk).exists()
    )
