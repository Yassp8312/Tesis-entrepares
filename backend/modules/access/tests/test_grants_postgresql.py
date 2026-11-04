"""T32/T33: integridad de concesiones; ninguna fila acredita autorización funcional."""

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

from modules.academics.models import AcademicScope, Institution
from modules.access.models import Capability, Grant
from modules.identity.models import Account
from modules.organizations.models import Organization

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
ENDED = CREATED + timedelta(days=1)
SCHEMA = {
    "access_capability": {
        "code": ("character varying(80)", False),
        "description": ("text", False),
        "is_delegable": ("boolean", False),
    },
    "access_grant": {
        "id": ("uuid", False),
        "account_id": ("uuid", False),
        "capability_code": ("character varying(80)", False),
        "scope_kind": ("character varying(16)", False),
        "academic_scope_id": ("uuid", True),
        "organization_id": ("uuid", True),
        "granted_by": ("uuid", False),
        "parent_grant_id": ("uuid", True),
        "source": ("character varying(24)", False),
        "valid_from": ("timestamp with time zone", False),
        "valid_until": ("timestamp with time zone", True),
        "ended_at": ("timestamp with time zone", True),
        "ended_by": ("uuid", True),
        "end_reason": ("text", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
}
REFERENCES = [
    ("account_id", "fk_t33_01", "identity_account"),
    ("granted_by", "fk_t33_02", "identity_account"),
    ("ended_by", "fk_t33_03", "identity_account"),
    ("capability_code", "fk_t33_04", "access_capability"),
    ("academic_scope_id", "fk_t33_05", "academics_scope"),
    ("organization_id", "fk_t33_06", "organizations_organization"),
    ("parent_grant_id", "fk_t33_07", "access_grant"),
]


def insert_row(table, values):
    key = "code" if table == "access_capability" else "id"
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {}").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.Placeholder() for _ in values),
                sql.Identifier(key),
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
    issuer, recipient, other, free = [
        Account.objects.create_user(f"concesion-{name}@example.org")
        for name in ("otorgante", "receptor", "otro", "libre")
    ]
    capability = Capability.objects.create(
        code="synthetic.capability", description="Capacidad sintética", is_delegable=True
    )
    other_capability = Capability.objects.create(
        code="synthetic.other", description="Otra capacidad sintética"
    )
    institution = Institution.objects.create(
        name="Institución sintética de concesiones", kind="university", origin="declared"
    )
    scope, other_scope = [
        AcademicScope.objects.create(
            institution=institution, name=f"Ámbito sintético {name}", kind="faculty"
        )
        for name in ("A", "B")
    ]
    organization, other_organization = [
        Organization.objects.create(
            name=f"Entidad sintética {name}", kind="other", created_by=issuer
        )
        for name in ("A", "B")
    ]
    parent = Grant.objects.create(
        account=issuer,
        capability=capability,
        scope_kind="global",
        granted_by=issuer,
        source="bootstrap",
    )
    return SimpleNamespace(
        issuer=issuer,
        recipient=recipient,
        other=other,
        free=free,
        capability=capability,
        other_capability=other_capability,
        institution=institution,
        scope=scope,
        other_scope=other_scope,
        organization=organization,
        other_organization=other_organization,
        parent=parent,
    )


def grant_values(records, kind="global"):
    values = {
        "account_id": records.recipient.pk,
        "capability_code": records.capability.pk,
        "scope_kind": kind,
        "granted_by": records.issuer.pk,
        "source": "administrative",
    }
    if kind == "academic":
        values["academic_scope_id"] = records.scope.pk
    if kind == "organization":
        values["organization_id"] = records.organization.pk
    return values


@pytest.mark.parametrize(
    "table,prefix,count", [("access_capability", "t32", 2), ("access_grant", "t33", 7)]
)
def test_schema_preserves_natural_key_columns_types_checks_and_indexes(table, prefix, count):
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
    assert [v["columns"] for v in constraints.values() if v["primary_key"]] == [
        ["code" if prefix == "t32" else "id"]
    ]
    actual = {
        k: v["columns"]
        for k, v in constraints.items()
        if (v["index"] or v["unique"]) and not v["primary_key"]
    }
    assert actual == (
        {"access_capability_code_72401c64_like": ["code"]}
        if prefix == "t32"
        else {
            "uq_t33_key01": ["id", "account_id"],
            "uq_t33_01": [
                "account_id",
                "capability_code",
                "scope_kind",
                "academic_scope_id",
                "organization_id",
            ],
            "ix_t33_02": ["account_id"],
            "ix_t33_03": ["granted_by"],
            "ix_t33_04": ["ended_by"],
            "ix_t33_05": ["capability_code"],
            "ix_t33_06": ["academic_scope_id"],
            "ix_t33_07": ["organization_id"],
            "ix_t33_08": ["parent_grant_id", "granted_by"],
        }
    )
    if prefix == "t32":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_indexdef('access_capability_code_72401c64_like'::regclass)"
            )
            assert "varchar_pattern_ops" in cursor.fetchone()[0]


def test_unique_index_uses_nulls_not_distinct_and_only_open_grants():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indisunique,indisvalid,indisready,indnullsnotdistinct,pg_get_expr(indpred,indrelid) FROM pg_index WHERE indexrelid='uq_t33_01'::regclass"
        )
        assert cursor.fetchone() == (True, True, True, True, "(ended_at IS NULL)")
        cursor.execute("SELECT pg_get_indexdef('uq_t33_01'::regclass)")
        assert "NULLS NOT DISTINCT" in cursor.fetchone()[0]


def test_seven_named_restrict_foreign_keys_preserve_parent_owner():
    expected = {
        name: f"FOREIGN KEY ({field}) REFERENCES {target}({'code' if target == 'access_capability' else 'id'}) ON DELETE RESTRICT"
        for field, name, target in REFERENCES
    }
    expected["fk_t33_07"] = (
        "FOREIGN KEY (parent_grant_id, granted_by) REFERENCES access_grant(id, account_id) ON DELETE RESTRICT"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid='access_grant'::regclass AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: definition for name, definition, *_ in rows} == expected
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


def test_capability_sql_default_does_not_delegate_or_grant_anything(records):
    before = Grant.objects.count()
    code = insert_row(
        "access_capability", {"code": "synthetic.new", "description": "Capacidad sintética nueva"}
    )
    capability = Capability.objects.get(pk=code)
    assert code == "synthetic.new" and str(capability) == code and not capability.is_delegable
    assert Grant.objects.count() == before


@pytest.mark.parametrize(
    "field,value,constraint",
    [
        ("code", "", "ck_t32_01"),
        ("code", "   ", "ck_t32_01"),
        ("description", "", "ck_t32_02"),
        ("description", "   ", "ck_t32_02"),
    ],
)
def test_capability_checks_reject_empty_text(field, value, constraint):
    assert_rejected(
        "access_capability",
        {"code": "synthetic.new", "description": "Capacidad sintética", field: value},
        constraint,
    )


def test_capability_code_is_a_unique_natural_key(records):
    assert_rejected(
        "access_capability",
        {"code": records.capability.pk, "description": "Duplicado sintético"},
        "access_capability_pkey",
    )


def test_grant_sql_defaults_and_partial_save(records):
    identifier = insert_row("access_grant", grant_values(records))
    grant = Grant.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(grant) == str(identifier)
    assert grant.valid_from == grant.created_at == grant.updated_at
    assert grant.valid_from.utcoffset() == timedelta(0) and grant.valid_until is None
    assert grant.ended_at is None and grant.ended_by_id is None and grant.parent_grant_id is None
    assert grant.capability_id == records.capability.code
    Grant.objects.filter(pk=identifier).update(updated_at=CREATED)
    grant.end_reason = "Nota sintética de persistencia"
    grant.save(update_fields=["end_reason"])
    grant.refresh_from_db()
    assert grant.updated_at > CREATED and grant.end_reason == "Nota sintética de persistencia"


@pytest.mark.parametrize("source", ["bootstrap", "delegation", "administrative"])
def test_declared_sources_persist_without_changing_technical_account_privileges(records, source):
    identifier = insert_row("access_grant", {**grant_values(records), "source": source})
    assert Grant.objects.get(pk=identifier).source == source
    records.recipient.refresh_from_db()
    assert (
        not records.recipient.has_usable_password()
        and not records.recipient.is_staff
        and not records.recipient.is_superuser
    )


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"scope_kind": "invalid"}, "ck_t33_01"),
        ({"source": "invalid"}, "ck_t33_02"),
        ({"scope_kind": "global", "academic_scope_id": "scope"}, "ck_t33_03"),
        ({"scope_kind": "global", "organization_id": "organization"}, "ck_t33_03"),
        ({"scope_kind": "academic"}, "ck_t33_03"),
        (
            {
                "scope_kind": "academic",
                "academic_scope_id": "scope",
                "organization_id": "organization",
            },
            "ck_t33_03",
        ),
        ({"scope_kind": "organization"}, "ck_t33_03"),
        (
            {
                "scope_kind": "organization",
                "organization_id": "organization",
                "academic_scope_id": "scope",
            },
            "ck_t33_03",
        ),
        ({"valid_from": CREATED, "valid_until": CREATED}, "ck_t33_05"),
        ({"valid_from": CREATED, "valid_until": CREATED - timedelta(microseconds=1)}, "ck_t33_05"),
        ({"ended_at": ENDED, "end_reason": "Cierre sintético"}, "ck_t33_06"),
        ({"ended_by": "free"}, "ck_t33_06"),
        ({"ended_at": ENDED, "ended_by": "free"}, "ck_t33_07"),
        ({"ended_at": ENDED, "ended_by": "free", "end_reason": ""}, "ck_t33_07"),
        ({"ended_at": ENDED, "ended_by": "free", "end_reason": "   "}, "ck_t33_07"),
    ],
)
def test_grant_checks_reject_raw_sql(records, changes, constraint):
    changes = {
        key: getattr(records, value).pk
        if key in ("academic_scope_id", "organization_id", "ended_by")
        and isinstance(value, str)
        and value in ("scope", "organization", "free")
        else value
        for key, value in changes.items()
    }
    assert_rejected("access_grant", {**grant_values(records), **changes}, constraint)


def test_grant_cannot_be_its_own_parent(records):
    identifier = uuid4()
    assert_rejected(
        "access_grant",
        {**grant_values(records), "id": identifier, "parent_grant_id": identifier},
        "ck_t33_04",
    )


@pytest.mark.parametrize("kind", ["global", "academic", "organization"])
def test_scope_kind_has_exactly_its_required_reference(records, kind):
    identifier = insert_row("access_grant", grant_values(records, kind))
    grant = Grant.objects.get(pk=identifier)
    assert grant.scope_kind == kind
    assert (grant.academic_scope_id, grant.organization_id) == {
        "global": (None, None),
        "academic": (records.scope.pk, None),
        "organization": (None, records.organization.pk),
    }[kind]


@pytest.mark.parametrize("valid_until", [None, CREATED + timedelta(microseconds=1)])
def test_validity_window_accepts_no_end_or_strictly_later_end(records, valid_until):
    identifier = insert_row(
        "access_grant", {**grant_values(records), "valid_from": CREATED, "valid_until": valid_until}
    )
    grant = Grant.objects.get(pk=identifier)
    assert grant.valid_from == CREATED and grant.valid_until == valid_until


@pytest.mark.parametrize("kind", ["global", "academic", "organization"])
def test_nulls_not_distinct_prevents_duplicate_open_grants_in_each_scope(records, kind):
    values = grant_values(records, kind)
    insert_row("access_grant", values)
    assert_rejected("access_grant", values, "uq_t33_01")


def test_different_people_capabilities_and_contexts_can_have_separate_grants(records):
    values = grant_values(records)
    for kind in ("global", "academic", "organization"):
        insert_row("access_grant", grant_values(records, kind))
    insert_row("access_grant", {**values, "account_id": records.other.pk})
    insert_row("access_grant", {**values, "capability_code": records.other_capability.pk})
    insert_row(
        "access_grant",
        {**grant_values(records, "academic"), "academic_scope_id": records.other_scope.pk},
    )
    insert_row(
        "access_grant",
        {**grant_values(records, "organization"), "organization_id": records.other_organization.pk},
    )
    assert Grant.objects.count() == 8  # Incluye la concesión raíz sintética.


def test_expired_unclosed_grant_keeps_unique_slot_until_closed_and_history_is_retained(records):
    values = grant_values(records)
    first = insert_row(
        "access_grant",
        {**values, "valid_from": CREATED, "valid_until": CREATED + timedelta(hours=1)},
    )
    assert_rejected("access_grant", values, "uq_t33_01")
    Grant.objects.filter(pk=first).update(
        ended_at=ENDED,
        ended_by=records.free,
        end_reason="Sustitución sintética de concesión caducada",
    )
    second = insert_row("access_grant", values)
    historical = insert_row(
        "access_grant",
        {
            **values,
            "ended_at": ENDED,
            "ended_by": records.free.pk,
            "end_reason": "Historial sintético",
        },
    )
    assert len({first, second, historical}) == 3
    assert Grant.objects.get(pk=first).valid_until == CREATED + timedelta(hours=1)
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Grant.objects.filter(pk=first).update(ended_at=None, ended_by=None)
    assert error.value.__cause__.diag.constraint_name == "uq_t33_01"


def test_delegation_parent_belongs_to_issuer_and_is_joinable(records):
    identifier = insert_row(
        "access_grant",
        {**grant_values(records), "source": "delegation", "parent_grant_id": records.parent.pk},
    )
    grant = Grant.objects.select_related("parent_grant").get(pk=identifier)
    assert grant.parent_grant == records.parent
    assert grant.parent_grant.account_id == grant.granted_by_id


def test_parent_cannot_be_taken_from_another_account(records):
    assert_rejected(
        "access_grant",
        {
            **grant_values(records),
            "source": "delegation",
            "parent_grant_id": records.parent.pk,
            "granted_by": records.other.pk,
        },
        "fk_t33_07",
    )


def test_parent_owner_cannot_change_under_a_child(records):
    insert_row(
        "access_grant",
        {**grant_values(records), "source": "delegation", "parent_grant_id": records.parent.pk},
    )
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Grant.objects.filter(pk=records.parent.pk).update(account=records.other)
    assert error.value.__cause__.diag.constraint_name == "fk_t33_07"


def test_child_issuer_cannot_change_away_from_parent_owner(records):
    identifier = insert_row(
        "access_grant",
        {**grant_values(records), "parent_grant_id": records.parent.pk, "source": "delegation"},
    )
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Grant.objects.filter(pk=identifier).update(granted_by=records.other)
    assert error.value.__cause__.diag.constraint_name == "fk_t33_07"


def values_for_reference(records, field):
    kind = (
        "academic"
        if field == "academic_scope_id"
        else "organization"
        if field == "organization_id"
        else "global"
    )
    values = grant_values(records, kind)
    if field == "ended_by":
        values.update(ended_at=ENDED, end_reason="Cierre sintético")
    if field == "parent_grant_id":
        values.update(source="delegation", parent_grant_id=records.parent.pk)
    return values


@pytest.mark.parametrize("field,constraint,target", REFERENCES)
def test_missing_foreign_targets_are_rejected(records, field, constraint, target):
    missing = "synthetic.missing" if field == "capability_code" else uuid4()
    assert_rejected(
        "access_grant", {**values_for_reference(records, field), field: missing}, constraint
    )


@pytest.mark.parametrize("field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_seven_references_restrict_sql_and_orm_deletion(
    records, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records.free,
        "access_capability": records.capability,
        "academics_scope": records.scope,
        "organizations_organization": records.organization,
        "access_grant": records.parent,
    }[target_table]
    identifier = insert_row(
        "access_grant", {**values_for_reference(records, field), field: target.pk}
    )
    key = "code" if target_table == "access_capability" else "id"
    with pytest.raises(RestrictedError if via_orm else IntegrityError) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE {}=%s").format(
                            sql.Identifier(target_table), sql.Identifier(key)
                        ),
                        [target.pk],
                    )
    if not via_orm:
        assert error.value.__cause__.diag.constraint_name == constraint
    assert (
        type(target).objects.filter(pk=target.pk).exists()
        and Grant.objects.filter(pk=identifier).exists()
    )


def test_catalog_and_grant_roll_back_with_outer_transaction(records):
    before = (Capability.objects.count(), Grant.objects.count())
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            code = insert_row(
                "access_capability",
                {"code": "synthetic.rollback", "description": "Capacidad sintética reversible"},
            )
            insert_row("access_grant", {**grant_values(records), "capability_code": code})
            raise RuntimeError("fallo sintético de coordinación")
    assert (Capability.objects.count(), Grant.objects.count()) == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["global", "academic", "organization"])
def test_concurrent_null_bearing_grants_do_not_duplicate_open_slot(records, kind):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    values = grant_values(records, kind)
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
                identifier = insert_row("access_grant", values)
            return "created", str(identifier), pid
        except IntegrityError as error:
            return "rejected", error.__cause__.diag.constraint_name, pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2), timeout=20))
    assert sorted(result[0] for result in results) == ["created", "rejected"]
    assert len({result[2] for result in results}) == 2
    assert next(result[1] for result in results if result[0] == "rejected") == "uq_t33_01"
    assert Grant.objects.filter(account=records.recipient).count() == 1


@pytest.mark.django_db(transaction=True)
def test_access_migration_reverses_and_restores_graph_preserving_other_modules():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-acceso@example.org")
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
        MigrationExecutor(connection).migrate([("access", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
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
    test_seven_named_restrict_foreign_keys_preserve_parent_owner()
    test_unique_index_uses_nulls_not_distinct_and_only_open_grants()
    assert (
        Account.objects.filter(pk=account.pk).exists()
        and AcademicScope.objects.filter(pk=scope.pk).exists()
    )
    assert Organization.objects.filter(pk=organization.pk).exists()
