"""Integridad e historial de T15–T17; cuentas y entidades exclusivamente sintéticas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.academics.models import Institution
from modules.identity.models import Account
from modules.organizations.models import Organization, OrganizationVerification, Representation

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
DECIDED = CREATED + timedelta(hours=1)
COMMON = {
    "id": ("uuid", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
SCHEMA = {
    "organizations_organization": {
        **COMMON,
        "name": ("character varying(200)", False),
        "kind": ("character varying(24)", False),
        "institution_id": ("uuid", True),
        "description": ("text", True),
        "created_by": ("uuid", False),
    },
    "organizations_verification": {
        **COMMON,
        "organization_id": ("uuid", False),
        "requested_by": ("uuid", False),
        "status": ("character varying(16)", False),
        "evidence_reference": ("text", True),
        "decided_by": ("uuid", True),
        "decided_at": ("timestamp with time zone", True),
        "decision_reason": ("text", True),
    },
    "organizations_representation": {
        **COMMON,
        "organization_id": ("uuid", False),
        "account_id": ("uuid", False),
        "granted_by": ("uuid", False),
        "revoked_at": ("timestamp with time zone", True),
        "revoked_by": ("uuid", True),
        "revocation_reason": ("text", True),
    },
}
MODELS = [Organization, OrganizationVerification, Representation]
REFERENCES = [
    ("organizations_organization", "institution_id", "fk_t15_01", "academics_institution"),
    ("organizations_organization", "created_by", "fk_t15_02", "identity_account"),
    ("organizations_verification", "organization_id", "fk_t16_01", "organizations_organization"),
    ("organizations_verification", "requested_by", "fk_t16_02", "identity_account"),
    ("organizations_verification", "decided_by", "fk_t16_03", "identity_account"),
    ("organizations_representation", "organization_id", "fk_t17_01", "organizations_organization"),
    ("organizations_representation", "account_id", "fk_t17_02", "identity_account"),
    ("organizations_representation", "granted_by", "fk_t17_03", "identity_account"),
    ("organizations_representation", "revoked_by", "fk_t17_04", "identity_account"),
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
    owner, member, reviewer = [
        Account.objects.create_user(f"{role}@example.org")
        for role in ("creador-organizacion", "representante", "revisor-organizacion")
    ]
    institution = Institution.objects.create(
        name="Institución sintética de prueba", kind="university", origin="curated"
    )
    organization = Organization.objects.create(
        name="Organización sintética de prueba", kind="private", created_by=owner
    )
    return owner, member, reviewer, institution, organization


def valid_values(table, records):
    owner, member, _, _, organization = records
    return {
        "organizations_organization": {
            "name": "Otra entidad sintética",
            "kind": "university",
            "created_by": owner.pk,
        },
        "organizations_verification": {
            "organization_id": organization.pk,
            "requested_by": member.pk,
        },
        "organizations_representation": {
            "organization_id": organization.pk,
            "account_id": member.pk,
            "granted_by": owner.pk,
        },
    }[table]


def decision_values(records, status="approved"):
    return {
        **valid_values("organizations_verification", records),
        "status": status,
        "created_at": CREATED,
        "decided_at": DECIDED,
        "decided_by": records[2].pk,
        "decision_reason": "Motivo sintético de comprobación",
    }


@pytest.mark.parametrize(
    "table,prefix,count,indexes",
    [
        (
            "organizations_organization",
            "t15",
            2,
            {"ix_t15_01": [], "ix_t15_02": ["institution_id"], "ix_t15_03": ["created_by"]},
        ),
        (
            "organizations_verification",
            "t16",
            3,
            {
                "uq_t16_01": ["organization_id"],
                "ix_t16_02": ["organization_id", "status"],
                "ix_t16_03": ["requested_by"],
                "ix_t16_04": ["decided_by"],
            },
        ),
        (
            "organizations_representation",
            "t17",
            2,
            {
                "uq_t17_01": ["organization_id", "account_id"],
                "ix_t17_02": ["organization_id"],
                "ix_t17_03": ["account_id"],
                "ix_t17_04": ["granted_by"],
                "ix_t17_05": ["revoked_by"],
            },
        ),
    ],
)
def test_schema_preserves_columns_checks_and_indexes(table, prefix, count, indexes):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull FROM pg_attribute "
            "WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",
            [table],
        )
        assert {name: (kind, nullable) for name, kind, nullable in cursor} == SCHEMA[table]
        constraints = connection.introspection.get_constraints(cursor, table)
        assert {k for k, v in constraints.items() if v["check"]} == {
            f"ck_{prefix}_{n:02}" for n in range(1, count + 1)
        }
        assert {k: v["columns"] for k, v in constraints.items() if v["index"]} == indexes
        assert {k for k, v in constraints.items() if v["unique"] and not v["primary_key"]} == (
            set() if prefix == "t15" else {f"uq_{prefix}_01"}
        )
        if prefix == "t15":
            cursor.execute("SELECT pg_get_indexdef('ix_t15_01'::regclass)")
            assert "lower((name)::text)" in cursor.fetchone()[0]


def test_partial_unique_indexes_have_the_exact_scope_and_valid_predicates():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexrelid::regclass::text,indisunique,indisvalid,indisready,"
            "pg_get_expr(indpred,indrelid) FROM pg_index WHERE indexrelid IN "
            "('uq_t16_01'::regclass,'uq_t17_01'::regclass) ORDER BY indexrelid::regclass::text"
        )
        rows = cursor.fetchall()
    assert [(name, unique, valid, ready) for name, unique, valid, ready, _ in rows] == [
        ("uq_t16_01", True, True, True),
        ("uq_t17_01", True, True, True),
    ]
    assert [predicate.replace("(", "").replace(")", "") for *_, predicate in rows] == [
        "status::text = 'pending'::text",
        "revoked_at IS NULL",
    ]


def test_all_nine_references_have_named_validated_restrict_foreign_keys():
    expected = {
        name: (table, f"FOREIGN KEY ({field}) REFERENCES {target}(id) ON DELETE RESTRICT")
        for table, field, name, target in REFERENCES
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,conrelid::regclass::text,pg_get_constraintdef(oid),"
            "confdeltype,condeferrable,convalidated FROM pg_constraint "
            "WHERE conrelid IN ('organizations_organization'::regclass,"
            "'organizations_verification'::regclass,'organizations_representation'::regclass) "
            "AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: (table, definition) for name, table, definition, *_ in rows} == expected
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


@pytest.mark.parametrize("model", MODELS)
def test_defaults_partial_save_and_no_automatic_personal_privileges(model, records):
    table = model._meta.db_table
    identifier = insert_row(table, valid_values(table, records))
    record = model.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(record) == str(identifier)
    assert record.created_at == record.updated_at and record.created_at.utcoffset() == timedelta(0)
    if model is OrganizationVerification:
        assert (
            record.status == "pending"
            and record.decided_by_id is None
            and record.decided_at is None
        )
        field, value = "evidence_reference", "Referencia sintética privada"
    elif model is Representation:
        assert record.revoked_at is None and record.revoked_by_id is None
        field, value = "revocation_reason", "Nota sintética de persistencia"
    else:
        assert record.institution_id is None and record.description is None
        field, value = "description", "Presentación sintética"
    model.objects.filter(pk=identifier).update(updated_at=CREATED)
    setattr(record, field, value)
    record.save(update_fields=[field])
    record.refresh_from_db()
    assert record.updated_at > CREATED and getattr(record, field) == value
    for account in records[:3]:
        account.refresh_from_db()
        assert (
            not account.has_usable_password() and not account.is_staff and not account.is_superuser
        )


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("organizations_organization", {"name": ""}, "ck_t15_01"),
        ("organizations_organization", {"name": "   "}, "ck_t15_01"),
        ("organizations_organization", {"kind": "invalid"}, "ck_t15_02"),
        ("organizations_verification", {"status": "invalid"}, "ck_t16_01"),
        ("organizations_verification", {"decided_at": DECIDED}, "ck_t16_02"),
        ("organizations_verification", {"decided_by": "reviewer"}, "ck_t16_02"),
        (
            "organizations_representation",
            {"revoked_at": DECIDED, "created_at": CREATED},
            "ck_t17_01",
        ),
        ("organizations_representation", {"revoked_by": "reviewer"}, "ck_t17_01"),
        (
            "organizations_representation",
            {"created_at": DECIDED, "revoked_at": CREATED, "revoked_by": "reviewer"},
            "ck_t17_02",
        ),
    ],
)
def test_checks_reject_sql_without_model_validation(records, table, changes, constraint):
    changes = {
        key: records[2].pk if value == "reviewer" else value for key, value in changes.items()
    }
    assert_rejected(table, {**valid_values(table, records), **changes}, constraint)


@pytest.mark.parametrize("status", ["approved", "rejected", "withdrawn"])
@pytest.mark.parametrize(
    "missing,constraint",
    [
        ("decided_at", "ck_t16_02"),
        ("decided_by", "ck_t16_03"),
        ("decision_reason", "ck_t16_03"),
        ("empty_reason", "ck_t16_03"),
    ],
)
def test_resolved_verification_requires_date_reviewer_and_reason(
    records, status, missing, constraint
):
    values = decision_values(records, status)
    if missing == "empty_reason":
        values["decision_reason"] = "   "
    else:
        values[missing] = None
    assert_rejected("organizations_verification", values, constraint)


@pytest.mark.parametrize("status", ["approved", "rejected", "withdrawn"])
def test_resolved_history_is_preserved_and_does_not_preclude_new_pending_request(records, status):
    first = insert_row("organizations_verification", decision_values(records, status))
    second = insert_row("organizations_verification", decision_values(records, status))
    pending = insert_row(
        "organizations_verification", valid_values("organizations_verification", records)
    )
    assert len({first, second, pending}) == 3
    assert OrganizationVerification.objects.filter(status="pending").count() == 1
    assert Representation.objects.count() == 0


def test_only_one_pending_request_per_organization_and_slot_reopens_after_resolution(records):
    table = "organizations_verification"
    values = valid_values(table, records)
    identifier = insert_row(table, values)
    assert_rejected(table, {**values, "requested_by": records[2].pk}, "uq_t16_01")
    OrganizationVerification.objects.filter(pk=identifier).update(
        status="rejected",
        decided_by=records[2],
        decided_at=DECIDED,
        decision_reason="Motivo sintético",
    )
    second = insert_row(table, values)
    assert second != identifier and OrganizationVerification.objects.count() == 2
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            OrganizationVerification.objects.filter(pk=identifier).update(
                status="pending", decided_by=None, decided_at=None
            )
    assert error.value.__cause__.diag.constraint_name == "uq_t16_01"


def test_one_unrevoked_representation_per_pair_preserves_regrant_history(records):
    table = "organizations_representation"
    values = {**valid_values(table, records), "created_at": CREATED}
    first = insert_row(table, values)
    assert_rejected(table, values, "uq_t17_01")
    Representation.objects.filter(pk=first).update(
        revoked_at=DECIDED, revoked_by=records[2], revocation_reason="Retiro sintético"
    )
    historical = insert_row(table, {**values, "revoked_at": DECIDED, "revoked_by": records[2].pk})
    current = insert_row(table, values)
    assert len({first, historical, current}) == 3
    assert Representation.objects.filter(revoked_at__isnull=True).count() == 1
    assert Representation.objects.filter(revoked_at__isnull=False).count() == 2
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Representation.objects.filter(pk=first).update(revoked_at=None, revoked_by=None)
    assert error.value.__cause__.diag.constraint_name == "uq_t17_01"


def test_representation_uniqueness_allows_other_accounts_and_organizations(records):
    table = "organizations_representation"
    values = valid_values(table, records)
    other = Organization.objects.create(
        name="Segunda entidad sintética", kind="other", created_by=records[0]
    )
    insert_row(table, values)
    insert_row(table, {**values, "account_id": records[2].pk})
    insert_row(table, {**values, "organization_id": other.pk})
    assert Representation.objects.filter(revoked_at__isnull=True).count() == 3


@pytest.mark.parametrize("revoked_at", [CREATED, DECIDED])
def test_revocation_date_can_equal_or_follow_creation(records, revoked_at):
    identifier = insert_row(
        "organizations_representation",
        {
            **valid_values("organizations_representation", records),
            "created_at": CREATED,
            "revoked_at": revoked_at,
            "revoked_by": records[2].pk,
        },
    )
    record = Representation.objects.get(pk=identifier)
    assert record.revoked_at == revoked_at and record.revoked_by == records[2]


def test_organization_homonyms_and_catalog_link_do_not_create_verification_or_representation(
    records,
):
    values = {
        **valid_values("organizations_organization", records),
        "institution_id": records[3].pk,
    }
    first = insert_row("organizations_organization", values)
    second = insert_row("organizations_organization", values)
    assert first != second
    assert OrganizationVerification.objects.count() == Representation.objects.count() == 0


@pytest.mark.parametrize("table,field,constraint,target", REFERENCES)
def test_missing_foreign_targets_are_rejected(records, table, field, constraint, target):
    values = valid_values(table, records)
    if field == "decided_by":
        values = decision_values(records)
    elif field == "revoked_by":
        values = {**values, "created_at": CREATED, "revoked_at": DECIDED}
    assert_rejected(table, {**values, field: uuid4()}, constraint)


@pytest.mark.parametrize("table,field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_referenced_rows_cannot_be_deleted_or_cascaded(
    records, table, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records[2],
        "academics_institution": records[3],
        "organizations_organization": records[4],
    }[target_table]
    values = {**valid_values(table, records), field: target.pk}
    if field == "decided_by":
        values = {**decision_values(records), field: target.pk}
    elif field == "revoked_by":
        values.update(created_at=CREATED, revoked_at=DECIDED)
    inserted = insert_row(table, values)
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
            sql.SQL("SELECT count(*) FROM {} WHERE id=%s").format(sql.Identifier(table)), [inserted]
        )
        assert cursor.fetchone()[0] == 1


def test_outer_transaction_rolls_back_all_three_owned_tables(records):
    before = {model: model.objects.count() for model in MODELS}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            identifier = insert_row(
                "organizations_organization", valid_values("organizations_organization", records)
            )
            for table in ("organizations_verification", "organizations_representation"):
                insert_row(table, {**valid_values(table, records), "organization_id": identifier})
            raise RuntimeError("fallo sintético de coordinación")
    assert {model: model.objects.count() for model in MODELS} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "table,constraint",
    [
        ("organizations_verification", "uq_t16_01"),
        ("organizations_representation", "uq_t17_01"),
    ],
)
def test_concurrent_insertions_cannot_create_duplicate_current_records(records, table, constraint):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    values = valid_values(table, records)
    barrier = Barrier(2)

    def worker(_):
        try:
            # Django mantiene una conexión independiente por hilo; no se comparten cursores.
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
def test_organization_migration_reverses_and_restores_the_complete_graph():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-organizacion@example.org")
    institution = Institution.objects.create(
        name="Institución conservada sintética", kind="other", origin="declared"
    )
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("organizations", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert Account.objects.filter(pk=account.pk).exists()
        assert Institution.objects.filter(pk=institution.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert not MigrationExecutor(connection).migration_plan(targets)
    test_all_nine_references_have_named_validated_restrict_foreign_keys()
    test_partial_unique_indexes_have_the_exact_scope_and_valid_predicates()
    assert Account.objects.filter(pk=account.pk).exists()
    assert Institution.objects.filter(pk=institution.pk).exists()
