"""T08–T11 sobre PostgreSQL: datos sintéticos, sin acreditar autoridades ni usuarios."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.academics.models import AcademicScope, Discipline, Institution, InstitutionalDomain
from modules.identity.models import Account

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
COMMON = {
    "id": ("uuid", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
SCHEMA = {
    "academics_institution": {
        **COMMON,
        "name": ("character varying(200)", False),
        "kind": ("character varying(24)", False),
        "origin": ("character varying(16)", False),
        "created_by": ("uuid", True),
    },
    "academics_scope": {
        **COMMON,
        "institution_id": ("uuid", False),
        "parent_id": ("uuid", True),
        "name": ("character varying(200)", False),
        "kind": ("character varying(16)", False),
    },
    "academics_discipline": {
        **COMMON,
        "name": ("character varying(200)", False),
        "origin": ("character varying(16)", False),
        "created_by": ("uuid", True),
    },
    "academics_domain": {
        **COMMON,
        "domain_ascii": ("character varying(253)", False),
        "institution_id": ("uuid", False),
        "status": ("character varying(16)", False),
        "evidence_reference": ("text", True),
        "decided_by": ("uuid", True),
        "decided_at": ("timestamp with time zone", True),
    },
}
MODELS = [Institution, AcademicScope, Discipline, InstitutionalDomain]


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
def catalogs():
    account = Account.objects.create_user("catalogos@example.org")
    first, second = [
        Institution.objects.create(
            name=f"Institución sintética {name}", kind="university", origin="curated"
        )
        for name in ("A", "B")
    ]
    parent = AcademicScope.objects.create(
        institution=first, name="Facultad sintética", kind="faculty"
    )
    return account, first, second, parent


def valid_values(table, catalogs):
    account, institution, _, _ = catalogs
    return {
        "academics_institution": {
            "name": "Institución sintética",
            "kind": "university",
            "origin": "declared",
            "created_by": account.pk,
        },
        "academics_scope": {
            "name": "Ámbito sintético",
            "kind": "career",
            "institution_id": institution.pk,
        },
        "academics_discipline": {
            "name": "Disciplina sintética",
            "origin": "declared",
            "created_by": account.pk,
        },
        "academics_domain": {
            "domain_ascii": "academia.example.org",
            "institution_id": institution.pk,
        },
    }[table]


@pytest.mark.parametrize(
    "table,prefix,count",
    [
        ("academics_institution", "t08", 3),
        ("academics_scope", "t09", 3),
        ("academics_discipline", "t10", 2),
        ("academics_domain", "t11", 4),
    ],
)
def test_real_schema_preserves_columns_types_checks_unique_keys_and_indexes(table, prefix, count):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull "
            "FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",
            [table],
        )
        assert {name: (kind, nullable) for name, kind, nullable in cursor} == SCHEMA[table]
        constraints = connection.introspection.get_constraints(cursor, table)
        assert {k for k, v in constraints.items() if v["check"]} == {
            f"ck_{prefix}_{n:02}" for n in range(1, count + 1)
        }
        assert {k for k, v in constraints.items() if v["index"]} == {
            f"ix_{prefix}_01",
            f"ix_{prefix}_02",
        }
        unique = {
            k: v["columns"] for k, v in constraints.items() if v["unique"] and not v["primary_key"]
        }
        assert (
            unique
            == {
                "academics_institution": {},
                "academics_discipline": {},
                "academics_scope": {"uq_t09_key01": ["id", "institution_id"]},
                "academics_domain": {"uq_t11_key01": ["domain_ascii"]},
            }[table]
        )
        if prefix in ("t08", "t10"):
            cursor.execute("SELECT pg_get_indexdef(%s::regclass)", [f"ix_{prefix}_01"])
            assert "lower((name)::text)" in cursor.fetchone()[0]
        else:
            assert constraints[f"ix_{prefix}_01"]["columns"] == ["institution_id"]
        assert (
            constraints[f"ix_{prefix}_02"]["columns"]
            == {
                "t08": ["created_by"],
                "t09": ["parent_id", "institution_id"],
                "t10": ["created_by"],
                "t11": ["decided_by"],
            }[prefix]
        )


def test_six_foreign_keys_are_validated_restrict_and_preserve_composite_parent():
    expected = {
        "fk_t08_01": (
            "academics_institution",
            "FOREIGN KEY (created_by) REFERENCES identity_account(id) ON DELETE RESTRICT",
        ),
        "fk_t09_01": (
            "academics_scope",
            "FOREIGN KEY (institution_id) REFERENCES academics_institution(id) ON DELETE RESTRICT",
        ),
        "fk_t09_02": (
            "academics_scope",
            "FOREIGN KEY (parent_id, institution_id) REFERENCES academics_scope(id, institution_id) ON DELETE RESTRICT",
        ),
        "fk_t10_01": (
            "academics_discipline",
            "FOREIGN KEY (created_by) REFERENCES identity_account(id) ON DELETE RESTRICT",
        ),
        "fk_t11_01": (
            "academics_domain",
            "FOREIGN KEY (institution_id) REFERENCES academics_institution(id) ON DELETE RESTRICT",
        ),
        "fk_t11_02": (
            "academics_domain",
            "FOREIGN KEY (decided_by) REFERENCES identity_account(id) ON DELETE RESTRICT",
        ),
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,conrelid::regclass::text,pg_get_constraintdef(oid),"
            "confdeltype,condeferrable,convalidated FROM pg_constraint "
            "WHERE conrelid IN ('academics_institution'::regclass,'academics_scope'::regclass,"
            "'academics_discipline'::regclass,'academics_domain'::regclass) AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: (table, definition) for name, table, definition, *_ in rows} == expected
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )
    assert not AcademicScope._meta.get_field("parent").db_constraint


@pytest.mark.parametrize("model", MODELS)
def test_sql_defaults_and_partial_update_timestamp(model, catalogs):
    table = model._meta.db_table
    identifier = insert_row(table, valid_values(table, catalogs))
    record = model.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(record) == str(identifier)
    assert record.created_at == record.updated_at
    assert record.created_at.utcoffset() == timedelta(0)
    if model is InstitutionalDomain:
        assert record.status == "pending" and record.evidence_reference is None
        field, value = "evidence_reference", "Referencia sintética privada"
    else:
        field, value = "name", "Nombre sintético modificado"
    model.objects.filter(pk=identifier).update(updated_at=CREATED)
    setattr(record, field, value)
    record.save(update_fields=[field])
    record.refresh_from_db()
    assert record.updated_at > CREATED and getattr(record, field) == value


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("academics_institution", {"name": ""}, "ck_t08_01"),
        ("academics_institution", {"name": "   "}, "ck_t08_01"),
        ("academics_institution", {"kind": "invalid"}, "ck_t08_02"),
        ("academics_institution", {"origin": "invalid"}, "ck_t08_03"),
        ("academics_scope", {"name": ""}, "ck_t09_01"),
        ("academics_scope", {"name": "   "}, "ck_t09_01"),
        ("academics_scope", {"kind": "invalid"}, "ck_t09_02"),
        ("academics_discipline", {"name": ""}, "ck_t10_01"),
        ("academics_discipline", {"name": "   "}, "ck_t10_01"),
        ("academics_discipline", {"origin": "invalid"}, "ck_t10_02"),
        ("academics_domain", {"domain_ascii": ""}, "ck_t11_01"),
        ("academics_domain", {"domain_ascii": "   "}, "ck_t11_01"),
        ("academics_domain", {"domain_ascii": "Academia.example.org"}, "ck_t11_03"),
        ("academics_domain", {"domain_ascii": " academia.example.org"}, "ck_t11_03"),
        ("academics_domain", {"domain_ascii": "academia.example.org "}, "ck_t11_03"),
        ("academics_domain", {"status": "invalid"}, "ck_t11_02"),
    ],
)
def test_checks_reject_direct_sql_without_model_validation(catalogs, table, changes, constraint):
    assert_rejected(table, {**valid_values(table, catalogs), **changes}, constraint)


def test_scope_cannot_be_its_own_parent(catalogs):
    identifier = uuid4()
    assert_rejected(
        "academics_scope",
        {
            **valid_values("academics_scope", catalogs),
            "id": identifier,
            "parent_id": identifier,
        },
        "ck_t09_03",
    )


@pytest.mark.parametrize("status", ["recognized", "withdrawn"])
@pytest.mark.parametrize(
    "missing", ["decided_by", "decided_at", "evidence_reference", "empty_evidence"]
)
def test_domain_decision_requires_reviewer_date_and_private_reference(catalogs, status, missing):
    values = {
        **valid_values("academics_domain", catalogs),
        "status": status,
        "decided_by": catalogs[0].pk,
        "decided_at": CREATED,
        "evidence_reference": "Referencia sintética privada",
    }
    if missing == "empty_evidence":
        values["evidence_reference"] = "   "
    else:
        values[missing] = None
    assert_rejected("academics_domain", values, "ck_t11_04")


@pytest.mark.parametrize("status", ["recognized", "withdrawn"])
def test_complete_domain_decision_persists_without_modifying_account(catalogs, status):
    account = catalogs[0]
    identifier = insert_row(
        "academics_domain",
        {
            **valid_values("academics_domain", catalogs),
            "status": status,
            "decided_by": account.pk,
            "decided_at": CREATED,
            "evidence_reference": "Referencia sintética privada",
        },
    )
    domain = InstitutionalDomain.objects.get(pk=identifier)
    assert domain.status == status and domain.decided_by == account
    assert domain.institution == catalogs[1]
    account.refresh_from_db()
    assert not account.has_usable_password() and not account.is_staff and not account.is_superuser


@pytest.mark.parametrize("model", [Institution, Discipline])
def test_homonyms_and_case_variants_are_not_merged_or_rejected(catalogs, model):
    table = model._meta.db_table
    first = insert_row(
        table, {**valid_values(table, catalogs), "name": "Nombre repetido sintético"}
    )
    second = insert_row(
        table, {**valid_values(table, catalogs), "name": "Nombre repetido sintético"}
    )
    third = insert_row(
        table, {**valid_values(table, catalogs), "name": "NOMBRE REPETIDO SINTÉTICO"}
    )
    assert len({first, second, third}) == 3


def test_exact_domain_is_unique_across_institutions_but_subdomain_is_distinct(catalogs):
    values = valid_values("academics_domain", catalogs)
    insert_row("academics_domain", values)
    assert_rejected(
        "academics_domain", {**values, "institution_id": catalogs[2].pk}, "uq_t11_key01"
    )
    insert_row("academics_domain", {**values, "domain_ascii": "sub.academia.example.org"})
    assert InstitutionalDomain.objects.count() == 2


def test_root_parent_and_child_are_joinable_within_institution(catalogs):
    _, institution, _, parent = catalogs
    identifier = insert_row(
        "academics_scope",
        {
            **valid_values("academics_scope", catalogs),
            "parent_id": parent.pk,
        },
    )
    child = AcademicScope.objects.select_related("parent", "institution").get(pk=identifier)
    assert parent.parent_id is None and child.parent == parent and child.institution == institution
    assert list(parent.children.values_list("pk", flat=True)) == [identifier]


@pytest.mark.parametrize("by_update", [False, True])
def test_parent_from_another_institution_is_rejected_on_insert_and_update(catalogs, by_update):
    _, _, second, parent = catalogs
    values = {**valid_values("academics_scope", catalogs), "institution_id": second.pk}
    if not by_update:
        assert_rejected("academics_scope", {**values, "parent_id": parent.pk}, "fk_t09_02")
    else:
        identifier = insert_row("academics_scope", values)
        with pytest.raises(IntegrityError) as error:
            with transaction.atomic():
                AcademicScope.objects.filter(pk=identifier).update(parent_id=parent.pk)
        assert error.value.__cause__.diag.constraint_name == "fk_t09_02"
        assert AcademicScope.objects.get(pk=identifier).parent_id is None


def test_parent_institution_cannot_change_under_existing_children(catalogs):
    _, _, second, parent = catalogs
    insert_row(
        "academics_scope", {**valid_values("academics_scope", catalogs), "parent_id": parent.pk}
    )
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            AcademicScope.objects.filter(pk=parent.pk).update(institution_id=second.pk)
    assert error.value.__cause__.diag.constraint_name == "fk_t09_02"
    parent.refresh_from_db()
    assert parent.institution_id == catalogs[1].pk


@pytest.mark.parametrize(
    "table,field,constraint",
    [
        ("academics_institution", "created_by", "fk_t08_01"),
        ("academics_scope", "institution_id", "fk_t09_01"),
        ("academics_scope", "parent_id", "fk_t09_02"),
        ("academics_discipline", "created_by", "fk_t10_01"),
        ("academics_domain", "institution_id", "fk_t11_01"),
        ("academics_domain", "decided_by", "fk_t11_02"),
    ],
)
def test_foreign_keys_reject_missing_targets(catalogs, table, field, constraint):
    assert_rejected(table, {**valid_values(table, catalogs), field: uuid4()}, constraint)


@pytest.mark.parametrize(
    "reference",
    [
        "institution_creator",
        "scope_institution",
        "scope_parent",
        "discipline_creator",
        "domain_institution",
        "domain_reviewer",
    ],
)
@pytest.mark.parametrize("via_orm", [False, True])
def test_referenced_rows_cannot_be_deleted(catalogs, reference, via_orm):
    account, institution, _, parent = catalogs
    table, target, constraint, extra = {
        "institution_creator": ("academics_institution", account, "fk_t08_01", {}),
        "scope_institution": ("academics_scope", institution, "fk_t09_01", {}),
        "scope_parent": ("academics_scope", parent, "fk_t09_02", {"parent_id": parent.pk}),
        "discipline_creator": ("academics_discipline", account, "fk_t10_01", {}),
        "domain_institution": ("academics_domain", institution, "fk_t11_01", {}),
        "domain_reviewer": ("academics_domain", account, "fk_t11_02", {"decided_by": account.pk}),
    }[reference]
    if reference == "domain_institution":
        # Aislar la FK del dominio: la institución A ya tiene el ámbito padre de la fixture.
        target, extra = catalogs[2], {"institution_id": catalogs[2].pk}
    insert_row(table, {**valid_values(table, catalogs), **extra})
    with pytest.raises(RestrictedError if via_orm else IntegrityError) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE id=%s").format(
                            sql.Identifier(target._meta.db_table)
                        ),
                        [target.pk],
                    )
    if not via_orm:
        assert error.value.__cause__.diag.constraint_name == constraint
    assert type(target).objects.filter(pk=target.pk).exists()


def test_catalog_changes_are_rolled_back_together(catalogs):
    before = {model: model.objects.count() for model in MODELS}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            for model in MODELS:
                insert_row(model._meta.db_table, valid_values(model._meta.db_table, catalogs))
            raise RuntimeError("fallo sintético de coordinación")
    assert {model: model.objects.count() for model in MODELS} == before


@pytest.mark.django_db(transaction=True)
def test_academics_migration_reverses_and_reapplies_preserving_identity():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-academica@example.org")
    try:
        MigrationExecutor(connection).migrate([("academics", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert Account.objects.filter(pk=account.pk).exists()
    finally:
        MigrationExecutor(connection).migrate([("academics", "0001_catalogs_and_scopes")])
    assert set(SCHEMA) <= set(connection.introspection.table_names())
    test_six_foreign_keys_are_validated_restrict_and_preserve_composite_parent()
    assert Account.objects.filter(pk=account.pk).exists()
