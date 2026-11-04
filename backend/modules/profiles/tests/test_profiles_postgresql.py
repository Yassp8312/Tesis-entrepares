"""T04–T07 con datos sintéticos; persistencia separada de exposición y verificación."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.academics.models import Discipline, Institution
from modules.identity.models import Account
from modules.profiles.models import Contact, Education, Merit, Profile

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
ENDED = CREATED + timedelta(days=1)
COMMON = {
    "id": ("uuid", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
SCHEMA = {
    "profiles_profile": {
        **COMMON,
        "account_id": ("uuid", False),
        "full_name": ("character varying(200)", False),
        "bio": ("text", True),
        "experience_summary": ("text", True),
        "experience_years": ("numeric(5,1)", True),
        "interests": ("text", True),
    },
    "profiles_education": {
        **COMMON,
        "profile_id": ("uuid", False),
        "discipline_id": ("uuid", False),
        "institution_id": ("uuid", False),
        "condition": ("character varying(16)", False),
        "ended_at": ("timestamp with time zone", True),
    },
    "profiles_contact": {
        **COMMON,
        "profile_id": ("uuid", False),
        "kind": ("character varying(16)", False),
        "value": ("character varying(320)", False),
        "label": ("character varying(80)", True),
        "is_visible": ("boolean", False),
        "sort_order": ("integer", False),
    },
    "profiles_merit": {
        **COMMON,
        "profile_id": ("uuid", False),
        "title": ("character varying(200)", False),
        "description": ("text", True),
        "awarded_on": ("date", True),
    },
}
MODELS = [Profile, Education, Contact, Merit]
REFERENCES = [
    ("profiles_profile", "account_id", "fk_t04_01", "identity_account"),
    ("profiles_education", "profile_id", "fk_t05_01", "profiles_profile"),
    ("profiles_education", "discipline_id", "fk_t05_02", "academics_discipline"),
    ("profiles_education", "institution_id", "fk_t05_03", "academics_institution"),
    ("profiles_contact", "profile_id", "fk_t06_01", "profiles_profile"),
    ("profiles_merit", "profile_id", "fk_t07_01", "profiles_profile"),
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
    account, other_account, new_account = [
        Account.objects.create_user(f"perfil-{name}@example.org")
        for name in ("uno", "dos", "nuevo")
    ]
    institution, other_institution = [
        Institution.objects.create(
            name=f"Institución sintética {name}", kind="university", origin="declared"
        )
        for name in ("A", "B")
    ]
    discipline, other_discipline = [
        Discipline.objects.create(name=f"Disciplina sintética {name}", origin="declared")
        for name in ("A", "B")
    ]
    profile = Profile.objects.create(account=account, full_name="Participante sintético A")
    other_profile = Profile.objects.create(
        account=other_account, full_name="Participante sintético B"
    )
    return SimpleNamespace(
        account=account,
        other_account=other_account,
        new_account=new_account,
        institution=institution,
        other_institution=other_institution,
        discipline=discipline,
        other_discipline=other_discipline,
        profile=profile,
        other_profile=other_profile,
    )


def valid_values(table, records):
    return {
        "profiles_profile": {
            "account_id": records.new_account.pk,
            "full_name": "Nuevo perfil sintético",
        },
        "profiles_education": {
            "profile_id": records.profile.pk,
            "discipline_id": records.discipline.pk,
            "institution_id": records.institution.pk,
            "condition": "student",
        },
        "profiles_contact": {
            "profile_id": records.profile.pk,
            "kind": "phone",
            "value": "+12025550123",
        },
        "profiles_merit": {"profile_id": records.profile.pk, "title": "Mérito sintético declarado"},
    }[table]


@pytest.mark.parametrize(
    "table,prefix,count,indexes",
    [
        ("profiles_profile", "t04", 2, {"uq_t04_key01": ["account_id"]}),
        (
            "profiles_education",
            "t05",
            1,
            {
                "uq_t05_01": ["profile_id", "discipline_id", "institution_id", "condition"],
                "ix_t05_02": ["profile_id"],
                "ix_t05_03": ["discipline_id"],
                "ix_t05_04": ["institution_id"],
            },
        ),
        ("profiles_contact", "t06", 3, {"uq_t06_01": ["profile_id", "kind", "value"]}),
        ("profiles_merit", "t07", 1, {"ix_t07_01": ["profile_id"]}),
    ],
)
def test_schema_preserves_exact_columns_checks_and_indexed_keys(table, prefix, count, indexes):
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
    assert {
        k: v["columns"]
        for k, v in constraints.items()
        if (v["index"] or v["unique"]) and not v["primary_key"]
    } == indexes
    assert {k for k, v in constraints.items() if v["unique"] and not v["primary_key"]} == {
        "t04": {"uq_t04_key01"},
        "t05": {"uq_t05_01"},
        "t06": {"uq_t06_01"},
        "t07": set(),
    }[prefix]


def test_unique_keys_have_exact_predicates_and_are_valid():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexrelid::regclass::text,indisunique,indisvalid,indisready,"
            "pg_get_expr(indpred,indrelid) FROM pg_index WHERE indexrelid IN "
            "('uq_t04_key01'::regclass,'uq_t05_01'::regclass,'uq_t06_01'::regclass) "
            "ORDER BY indexrelid::regclass::text"
        )
        rows = cursor.fetchall()
    assert [(name, unique, valid, ready) for name, unique, valid, ready, _ in rows] == [
        (name, True, True, True) for name in ("uq_t04_key01", "uq_t05_01", "uq_t06_01")
    ]
    assert [predicate for *_, predicate in rows] == [None, "(ended_at IS NULL)", None]


def test_six_foreign_keys_preserve_named_restrict_actions():
    expected = {
        name: (table, f"FOREIGN KEY ({field}) REFERENCES {target}(id) ON DELETE RESTRICT")
        for table, field, name, target in REFERENCES
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,conrelid::regclass::text,pg_get_constraintdef(oid),"
            "confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid IN "
            "('profiles_profile'::regclass,'profiles_education'::regclass,"
            "'profiles_contact'::regclass,'profiles_merit'::regclass) AND contype='f'"
        )
        rows = cursor.fetchall()
    assert {name: (table, definition) for name, table, definition, *_ in rows} == expected
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


@pytest.mark.parametrize("model", MODELS)
def test_sql_defaults_partial_save_and_safe_representation(model, records):
    table = model._meta.db_table
    identifier = insert_row(table, valid_values(table, records))
    record = model.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(record) == str(identifier)
    assert record.created_at == record.updated_at and record.created_at.utcoffset() == timedelta(0)
    if model is Profile:
        assert record.experience_years is None and record.bio is None
        field, value = "bio", "Presentación sintética"
    elif model is Education:
        assert record.ended_at is None
        field, value = "ended_at", datetime.now(UTC)
    elif model is Contact:
        assert record.is_visible is True and record.sort_order == 0 and record.label is None
        field, value = "label", "Contacto sintético"
    else:
        assert record.awarded_on is None and record.description is None
        field, value = "description", "Mérito sin aval, para pruebas"
    created_at = record.created_at
    model.objects.filter(pk=identifier).update(updated_at=CREATED)
    setattr(record, field, value)
    record.save(update_fields=[field])
    record.refresh_from_db()
    assert record.updated_at > CREATED and record.created_at == created_at
    assert getattr(record, field) == value


@pytest.mark.parametrize(
    "years", [None, Decimal("0.0"), Decimal("0.5"), Decimal("12.3"), Decimal("9999.9")]
)
def test_nullable_decimal_experience_preserves_stored_precision(records, years):
    identifier = insert_row(
        "profiles_profile", {**valid_values("profiles_profile", records), "experience_years": years}
    )
    assert Profile.objects.get(pk=identifier).experience_years == years


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("profiles_profile", {"full_name": ""}, "ck_t04_01"),
        ("profiles_profile", {"full_name": "   "}, "ck_t04_01"),
        ("profiles_profile", {"experience_years": Decimal("-0.1")}, "ck_t04_02"),
        ("profiles_education", {"condition": "professional"}, "ck_t05_01"),
        ("profiles_contact", {"kind": "invalid"}, "ck_t06_01"),
        ("profiles_contact", {"value": ""}, "ck_t06_02"),
        ("profiles_contact", {"value": "   "}, "ck_t06_02"),
        ("profiles_contact", {"sort_order": -1}, "ck_t06_03"),
        ("profiles_merit", {"title": ""}, "ck_t07_01"),
        ("profiles_merit", {"title": "   "}, "ck_t07_01"),
    ],
)
def test_checks_reject_direct_sql_without_model_validation(records, table, changes, constraint):
    assert_rejected(table, {**valid_values(table, records), **changes}, constraint)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("email", "perfil-sintetico@example.org"),
        ("phone", "+12025550123"),
        ("whatsapp", "+12025550123"),
        ("telegram", "entrepares_synthetic"),
    ],
)
def test_all_declared_contact_channels_can_be_stored(records, kind, value):
    identifier = insert_row(
        "profiles_contact",
        {**valid_values("profiles_contact", records), "kind": kind, "value": value},
    )
    contact = Contact.objects.get(pk=identifier)
    assert (contact.kind, contact.value) == (kind, value)


def test_only_one_profile_per_account_and_existing_profile_remains_intact(records):
    assert_rejected(
        "profiles_profile",
        {"account_id": records.account.pk, "full_name": "Duplicado sintético"},
        "uq_t04_key01",
    )
    assert Profile.objects.filter(account=records.account).get().pk == records.profile.pk


def test_current_education_is_unique_but_history_and_redeclaration_are_kept(records):
    table = "profiles_education"
    values = {**valid_values(table, records), "created_at": CREATED}
    first = insert_row(table, values)
    assert_rejected(table, values, "uq_t05_01")
    Education.objects.filter(pk=first).update(ended_at=ENDED)
    historical = insert_row(table, {**values, "ended_at": ENDED})
    current = insert_row(table, values)
    assert len({first, historical, current}) == 3
    assert Education.objects.filter(ended_at__isnull=True).count() == 1
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Education.objects.filter(pk=first).update(ended_at=None)
    assert error.value.__cause__.diag.constraint_name == "uq_t05_01"


@pytest.mark.parametrize(
    "dimension", ["profile_id", "discipline_id", "institution_id", "condition"]
)
def test_education_uniqueness_includes_all_four_dimensions(records, dimension):
    table = "profiles_education"
    values = valid_values(table, records)
    insert_row(table, values)
    alternative = {
        "profile_id": records.other_profile.pk,
        "discipline_id": records.other_discipline.pk,
        "institution_id": records.other_institution.pk,
        "condition": "graduate",
    }[dimension]
    insert_row(table, {**values, dimension: alternative})
    assert Education.objects.filter(ended_at__isnull=True).count() == 2


def test_student_to_graduate_history_keeps_profile_and_account(records):
    values = {**valid_values("profiles_education", records), "created_at": CREATED}
    student = insert_row("profiles_education", values)
    with transaction.atomic():
        Education.objects.filter(pk=student).update(ended_at=ENDED)
        graduate = insert_row(
            "profiles_education", {**values, "condition": "graduate", "created_at": ENDED}
        )
    assert Education.objects.get(pk=student).ended_at == ENDED
    assert Education.objects.get(pk=graduate).ended_at is None
    assert Profile.objects.get(pk=records.profile.pk).account_id == records.account.pk
    records.account.refresh_from_db()
    assert not records.account.is_staff and not records.account.is_superuser


def test_hidden_contact_is_retained_and_cannot_bypass_duplicate_check(records):
    table = "profiles_contact"
    values = valid_values(table, records)
    identifier = insert_row(table, values)
    Contact.objects.filter(pk=identifier).update(is_visible=False)
    assert_rejected(table, {**values, "is_visible": False}, "uq_t06_01")
    assert_rejected(table, {**values, "is_visible": True}, "uq_t06_01")
    contact = Contact.objects.get(pk=identifier)
    assert not contact.is_visible and contact.value == values["value"]


@pytest.mark.parametrize("dimension", ["profile_id", "kind", "value"])
def test_contact_uniqueness_is_per_profile_channel_and_value(records, dimension):
    table = "profiles_contact"
    values = valid_values(table, records)
    insert_row(table, values)
    alternative = {
        "profile_id": records.other_profile.pk,
        "kind": "whatsapp",
        "value": "+12025550124",
    }[dimension]
    insert_row(table, {**values, dimension: alternative})
    assert Contact.objects.count() == 2


def test_merits_remain_declarations_with_optional_date_and_repeatable_title(records):
    values = {**valid_values("profiles_merit", records), "awarded_on": date(2025, 1, 1)}
    first = insert_row("profiles_merit", values)
    second = insert_row("profiles_merit", values)
    assert first != second and Merit.objects.get(pk=first).awarded_on == values["awarded_on"]
    records.account.refresh_from_db()
    assert not records.account.has_usable_password() and not records.account.is_staff


@pytest.mark.parametrize("table,field,constraint,target", REFERENCES)
def test_missing_foreign_targets_are_rejected(records, table, field, constraint, target):
    assert_rejected(table, {**valid_values(table, records), field: uuid4()}, constraint)


@pytest.mark.parametrize("table,field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_references_prevent_accidental_deletion_and_cascade(
    records, table, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records.new_account,
        "profiles_profile": records.profile,
        "academics_discipline": records.discipline,
        "academics_institution": records.institution,
    }[target_table]
    identifier = insert_row(table, {**valid_values(table, records), field: target.pk})
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


def test_outer_transaction_rolls_back_profile_and_all_declarations(records):
    before = {model: model.objects.count() for model in MODELS}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            identifier = insert_row("profiles_profile", valid_values("profiles_profile", records))
            for table in ("profiles_education", "profiles_contact", "profiles_merit"):
                insert_row(table, {**valid_values(table, records), "profile_id": identifier})
            raise RuntimeError("fallo sintético de coordinación")
    assert {model: model.objects.count() for model in MODELS} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "table,constraint",
    [
        ("profiles_profile", "uq_t04_key01"),
        ("profiles_education", "uq_t05_01"),
        ("profiles_contact", "uq_t06_01"),
    ],
)
def test_concurrent_insertions_cannot_duplicate_profiles_current_education_or_contacts(
    records, table, constraint
):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    values = valid_values(table, records)
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
        cursor.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
                sql.Identifier(table),
                sql.SQL(" AND ").join(
                    sql.SQL("{}=%s").format(sql.Identifier(key)) for key in values
                ),
            ),
            list(values.values()),
        )
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_profile_migration_reverses_and_restores_graph_preserving_catalogs_and_identity():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-perfil@example.org")
    institution = Institution.objects.create(
        name="Institución sintética conservada", kind="other", origin="declared"
    )
    discipline = Discipline.objects.create(
        name="Disciplina sintética conservada", origin="declared"
    )
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("profiles", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert Account.objects.filter(pk=account.pk).exists()
        assert Institution.objects.filter(pk=institution.pk).exists()
        assert Discipline.objects.filter(pk=discipline.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert not MigrationExecutor(connection).migration_plan(targets)
    test_six_foreign_keys_preserve_named_restrict_actions()
    test_unique_keys_have_exact_predicates_and_are_valid()
    assert Account.objects.filter(pk=account.pk).exists()
    assert Institution.objects.filter(pk=institution.pk).exists()
    assert Discipline.objects.filter(pk=discipline.pk).exists()
