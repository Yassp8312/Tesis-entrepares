"""T18–T22: integridad real, financiación y conservación con datos sintéticos."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.db import DataError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.academics.models import Discipline
from modules.identity.models import Account
from modules.opportunities.models import (
    Funding,
    LifecycleEvent,
    Need,
    Opportunity,
    OpportunityContact,
)
from modules.organizations.models import Organization, Representation
from modules.profiles.models import Contact, Profile

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=31)
COMMON = {
    "id": ("uuid", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
SCHEMA = {
    "opportunities_opportunity": {
        **COMMON,
        "owner_account_id": ("uuid", True),
        "owner_organization_id": ("uuid", True),
        "author_id": ("uuid", False),
        "title": ("character varying(200)", False),
        "description": ("text", False),
        "area": ("character varying(150)", False),
        "responsible_label": ("character varying(200)", False),
        "lifecycle": ("character varying(16)", False),
        "visibility": ("character varying(16)", False),
        "published_at": ("timestamp with time zone", True),
        "expires_at": ("timestamp with time zone", True),
        "row_version": ("integer", False),
        "validity_revision": ("integer", False),
    },
    "opportunities_lifecycle_event": {
        "id": ("uuid", False),
        "opportunity_id": ("uuid", False),
        "validity_revision": ("integer", False),
        "event_kind": ("character varying(16)", False),
        "actor_id": ("uuid", True),
        "from_state": ("character varying(16)", False),
        "to_state": ("character varying(16)", False),
        "previous_expires_at": ("timestamp with time zone", True),
        "new_expires_at": ("timestamp with time zone", False),
        "created_at": ("timestamp with time zone", False),
    },
    "opportunities_need": {
        **COMMON,
        "opportunity_id": ("uuid", False),
        "description": ("text", False),
        "discipline_id": ("uuid", True),
        "sort_order": ("integer", False),
    },
    "opportunities_funding": {
        "opportunity_id": ("uuid", False),
        "estimated_amount": ("numeric(18,2)", False),
        "currency_code": ("character varying(3)", False),
        "coverage": ("character varying(16)", False),
        "payment_kind": ("character varying(16)", False),
        "payment_detail": ("text", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "opportunities_contact": {
        **COMMON,
        "opportunity_id": ("uuid", False),
        "kind": ("character varying(16)", False),
        "value": ("character varying(320)", False),
        "label": ("character varying(80)", True),
        "sort_order": ("integer", False),
    },
}
MODELS = {
    "opportunities_opportunity": Opportunity,
    "opportunities_lifecycle_event": LifecycleEvent,
    "opportunities_need": Need,
    "opportunities_funding": Funding,
    "opportunities_contact": OpportunityContact,
}
REFERENCES = [
    ("opportunities_opportunity", "owner_account_id", "fk_t18_01", "identity_account"),
    (
        "opportunities_opportunity",
        "owner_organization_id",
        "fk_t18_02",
        "organizations_organization",
    ),
    ("opportunities_opportunity", "author_id", "fk_t18_03", "identity_account"),
    ("opportunities_lifecycle_event", "opportunity_id", "fk_t19_01", "opportunities_opportunity"),
    ("opportunities_lifecycle_event", "actor_id", "fk_t19_02", "identity_account"),
    ("opportunities_need", "opportunity_id", "fk_t20_01", "opportunities_opportunity"),
    ("opportunities_need", "discipline_id", "fk_t20_02", "academics_discipline"),
    ("opportunities_funding", "opportunity_id", "fk_t21_01", "opportunities_opportunity"),
    ("opportunities_contact", "opportunity_id", "fk_t22_01", "opportunities_opportunity"),
]


def insert_row(table, values):
    pk = "opportunity_id" if table == "opportunities_funding" else "id"
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {}").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.Placeholder() for _ in values),
                sql.Identifier(pk),
            ),
            list(values.values()),
        )
        return cursor.fetchone()[0]


def assert_rejected(table, values, constraint):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            insert_row(table, values)
    assert error.value.__cause__.diag.constraint_name == constraint


def opportunity_values(records, organizational=False):
    return {
        "author_id": records.author.pk,
        "owner_organization_id" if organizational else "owner_account_id": records.organization.pk
        if organizational
        else records.owner.pk,
        "title": "Proyecto sintético de colaboración",
        "description": "Descripción sintética del proyecto y su necesidad",
        "area": "Área sintética",
        "responsible_label": "Responsable sintético",
    }


def event_values(records):
    return {
        "opportunity_id": records.opportunity.pk,
        "validity_revision": 1,
        "event_kind": "publish",
        "actor_id": records.author.pk,
        "from_state": "draft",
        "to_state": "active",
        "new_expires_at": END,
    }


def funding_values(records):
    return {
        "opportunity_id": records.opportunity.pk,
        "estimated_amount": Decimal("1234.56"),
        "currency_code": "CUP",
        "coverage": "project",
        "payment_kind": "one_off",
    }


def contact_values(records):
    return {
        "opportunity_id": records.opportunity.pk,
        "kind": "email",
        "value": "publico-sintetico@example.org",
    }


def values_for_table(records, table):
    return {
        "opportunities_opportunity": lambda: opportunity_values(records),
        "opportunities_lifecycle_event": lambda: event_values(records),
        "opportunities_need": lambda: {
            "opportunity_id": records.opportunity.pk,
            "description": "Necesidad sintética abierta",
        },
        "opportunities_funding": lambda: funding_values(records),
        "opportunities_contact": lambda: contact_values(records),
    }[table]()


@pytest.fixture
def records():
    owner, author, free = [
        Account.objects.create_user(f"oportunidades-{name}@example.org")
        for name in ("titular", "autor", "libre")
    ]
    organization = Organization.objects.create(
        name="Entidad sintética de oportunidades", kind="other", created_by=owner
    )
    discipline = Discipline.objects.create(name="Disciplina sintética abierta", origin="declared")
    records = SimpleNamespace(
        owner=owner, author=author, free=free, organization=organization, discipline=discipline
    )
    records.opportunity = Opportunity.objects.create(**opportunity_values(records))
    return records


@pytest.mark.parametrize("table", SCHEMA)
def test_fifty_columns_and_twenty_six_checks_match_design(table):
    number, count = {
        "opportunities_opportunity": (18, 11),
        "opportunities_lifecycle_event": (19, 5),
        "opportunities_need": (20, 2),
        "opportunities_funding": (21, 5),
        "opportunities_contact": (22, 3),
    }[table]
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


def test_nine_restrict_foreign_keys_have_exact_names_and_targets():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname,pg_get_constraintdef(oid),confdeltype,condeferrable,convalidated FROM pg_constraint WHERE conrelid=ANY(%s::regclass[]) AND contype='f'",
            [list(SCHEMA)],
        )
        rows = cursor.fetchall()
    assert {name: definition for name, definition, *_ in rows} == {
        name: f"FOREIGN KEY ({field}) REFERENCES {target}(id) ON DELETE RESTRICT"
        for table, field, name, target in REFERENCES
    }
    assert all(
        (delete, deferred, validated) == ("r", False, True)
        for *_, delete, deferred, validated in rows
    )


def test_indexes_preserve_expiry_filter_sort_expression_and_unique_keys():
    expected = {
        **{f"ix_t18_{n:02}": None for n in range(1, 7)},
        "ix_t19_01": None,
        "ix_t20_01": None,
        "ix_t20_02": None,
        "uq_t19_key01": None,
        "uq_t22_01": None,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,pg_get_indexdef(i.indexrelid),pg_get_expr(i.indpred,i.indrelid),i.indisunique FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=ANY(%s::regclass[]) AND NOT i.indisprimary",
            [list(SCHEMA)],
        )
        indexes = {
            name: (definition, predicate, unique) for name, definition, predicate, unique in cursor
        }
        constraints = {
            table: connection.introspection.get_constraints(cursor, table) for table in SCHEMA
        }
    assert set(indexes) == set(expected)
    assert "expires_at" in indexes["ix_t18_01"][0] and "active" in indexes["ix_t18_01"][1]
    assert "published_at DESC, id" in indexes["ix_t18_02"][0]
    assert "lower((area)::text)" in indexes["ix_t18_03"][0]
    assert all(
        predicate is None for name, (_, predicate, _) in indexes.items() if name != "ix_t18_01"
    )
    assert {name for name, (_, _, unique) in indexes.items() if unique} == {
        "uq_t19_key01",
        "uq_t22_01",
    }
    assert constraints["opportunities_lifecycle_event"]["uq_t19_key01"]["columns"] == [
        "opportunity_id",
        "validity_revision",
    ]
    assert constraints["opportunities_contact"]["uq_t22_01"]["columns"] == [
        "opportunity_id",
        "kind",
        "value",
    ]
    assert constraints["opportunities_funding"]["opportunities_funding_pkey"]["columns"] == [
        "opportunity_id"
    ]


@pytest.mark.parametrize("organizational", [False, True])
def test_exclusive_owner_does_not_replace_material_author(records, organizational):
    identifier = insert_row(
        "opportunities_opportunity", opportunity_values(records, organizational)
    )
    opportunity = Opportunity.objects.get(pk=identifier)
    assert opportunity.author_id == records.author.pk
    assert opportunity.owner_account_id == (None if organizational else records.owner.pk)
    assert opportunity.owner_organization_id == (
        records.organization.pk if organizational else None
    )


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"owner_account_id": None}, "ck_t18_01"),
        ({"owner_organization_id": "organization"}, "ck_t18_01"),
        ({"title": ""}, "ck_t18_02"),
        ({"title": "   "}, "ck_t18_02"),
        ({"description": ""}, "ck_t18_03"),
        ({"description": "   "}, "ck_t18_03"),
        ({"area": ""}, "ck_t18_04"),
        ({"area": "   "}, "ck_t18_04"),
        ({"responsible_label": ""}, "ck_t18_05"),
        ({"responsible_label": "   "}, "ck_t18_05"),
        ({"lifecycle": "invalid"}, "ck_t18_06"),
        ({"visibility": "invalid"}, "ck_t18_07"),
        ({"row_version": 0}, "ck_t18_08"),
        ({"row_version": -1}, "ck_t18_08"),
        ({"validity_revision": -1}, "ck_t18_09"),
        ({"published_at": START, "expires_at": START}, "ck_t18_11"),
        ({"published_at": END, "expires_at": START}, "ck_t18_11"),
    ],
)
def test_opportunity_checks_reject_incompatible_direct_sql(records, changes, constraint):
    if changes.get("owner_organization_id") == "organization":
        changes = {**changes, "owner_organization_id": records.organization.pk}
    assert_rejected(
        "opportunities_opportunity", {**opportunity_values(records), **changes}, constraint
    )


@pytest.mark.parametrize("lifecycle", ["active", "closed", "expired"])
@pytest.mark.parametrize("missing", ["published_at", "expires_at", "validity_revision"])
def test_non_draft_requires_both_dates_and_positive_revision(records, lifecycle, missing):
    values = {
        **opportunity_values(records),
        "lifecycle": lifecycle,
        "published_at": START,
        "expires_at": END,
        "validity_revision": 1,
    }
    values[missing] = 0 if missing == "validity_revision" else None
    assert_rejected("opportunities_opportunity", values, "ck_t18_10")


@pytest.mark.parametrize("lifecycle", ["active", "closed", "expired"])
def test_lifecycle_does_not_erase_dates_or_infer_effective_activity(records, lifecycle):
    identifier = insert_row(
        "opportunities_opportunity",
        {
            **opportunity_values(records),
            "lifecycle": lifecycle,
            "visibility": "hidden",
            "published_at": START,
            "expires_at": END,
            "validity_revision": 2,
        },
    )
    opportunity = Opportunity.objects.get(pk=identifier)
    assert (opportunity.published_at, opportunity.expires_at, opportunity.validity_revision) == (
        START,
        END,
        2,
    )
    # Incluso lifecycle=active puede estar vencido por tiempo o moderado: se evalúa al consultar.
    assert opportunity.visibility == "hidden"


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"event_kind": "invalid"}, "ck_t19_01"),
        ({"from_state": "invalid"}, "ck_t19_02"),
        ({"to_state": "draft"}, "ck_t19_03"),
        ({"validity_revision": 0}, "ck_t19_04"),
        ({"validity_revision": -1}, "ck_t19_04"),
        ({"actor_id": None}, "ck_t19_05"),
        ({"event_kind": "expire"}, "ck_t19_05"),
    ],
)
def test_lifecycle_history_checks(records, changes, constraint):
    assert_rejected(
        "opportunities_lifecycle_event", {**event_values(records), **changes}, constraint
    )


@pytest.mark.parametrize(
    "kind,source,target",
    [
        ("publish", "draft", "active"),
        ("close", "active", "closed"),
        ("extend", "active", "active"),
        ("expire", "active", "expired"),
        ("reactivate", "closed", "active"),
    ],
)
def test_each_event_kind_preserves_previous_and_new_deadlines(records, kind, source, target):
    values = {
        **event_values(records),
        "event_kind": kind,
        "from_state": source,
        "to_state": target,
        "actor_id": None if kind == "expire" else records.author.pk,
        "previous_expires_at": END,
        "new_expires_at": END + timedelta(days=1),
    }
    identifier = insert_row("opportunities_lifecycle_event", values)
    event = LifecycleEvent.objects.get(pk=identifier)
    assert (event.previous_expires_at, event.new_expires_at) == (END, values["new_expires_at"])


@pytest.mark.parametrize(
    "table,changes,constraint",
    [
        ("opportunities_need", {"description": ""}, "ck_t20_01"),
        ("opportunities_need", {"description": "   "}, "ck_t20_01"),
        ("opportunities_need", {"sort_order": -1}, "ck_t20_02"),
        ("opportunities_funding", {"estimated_amount": Decimal("-0.01")}, "ck_t21_01"),
        ("opportunities_funding", {"currency_code": "cup"}, "ck_t21_02"),
        ("opportunities_funding", {"currency_code": "CU"}, "ck_t21_02"),
        ("opportunities_funding", {"currency_code": "C1P"}, "ck_t21_02"),
        ("opportunities_funding", {"currency_code": ""}, "ck_t21_02"),
        ("opportunities_funding", {"payment_kind": "other", "payment_detail": None}, "ck_t21_03"),
        ("opportunities_funding", {"payment_kind": "other", "payment_detail": ""}, "ck_t21_03"),
        ("opportunities_funding", {"payment_kind": "other", "payment_detail": "   "}, "ck_t21_03"),
        ("opportunities_funding", {"coverage": "invalid"}, "ck_t21_04"),
        ("opportunities_funding", {"payment_kind": "invalid"}, "ck_t21_05"),
        ("opportunities_contact", {"kind": "invalid"}, "ck_t22_01"),
        ("opportunities_contact", {"value": ""}, "ck_t22_02"),
        ("opportunities_contact", {"value": "   "}, "ck_t22_02"),
        ("opportunities_contact", {"sort_order": -1}, "ck_t22_03"),
    ],
)
def test_need_funding_and_public_contact_checks(records, table, changes, constraint):
    assert_rejected(table, {**values_for_table(records, table), **changes}, constraint)


@pytest.mark.parametrize("coverage", ["project", "collaboration"])
@pytest.mark.parametrize("kind", ["one_off", "monthly", "other"])
def test_funding_accepts_both_coverages_and_declared_payment_modalities(records, coverage, kind):
    identifier = insert_row(
        "opportunities_funding",
        {
            **funding_values(records),
            "coverage": coverage,
            "payment_kind": kind,
            "payment_detail": "Por hitos sintéticos" if kind == "other" else None,
        },
    )
    funding = Funding.objects.get(pk=identifier)
    assert funding.estimated_amount == Decimal("1234.56") and funding.pk == records.opportunity.pk
    assert funding.coverage == coverage and funding.payment_kind == kind


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("9999999999999999.99")])
def test_declared_amount_preserves_exact_numeric_precision_and_zero(records, amount):
    insert_row("opportunities_funding", {**funding_values(records), "estimated_amount": amount})
    assert Funding.objects.get(pk=records.opportunity.pk).estimated_amount == amount


def test_amount_exceeding_numeric_capacity_is_rejected(records):
    with pytest.raises(DataError):
        with transaction.atomic():
            insert_row(
                "opportunities_funding",
                {**funding_values(records), "estimated_amount": Decimal("10000000000000000.00")},
            )


def test_need_supports_free_description_with_or_without_catalog_discipline(records):
    first = insert_row("opportunities_need", values_for_table(records, "opportunities_need"))
    second = insert_row(
        "opportunities_need",
        {**values_for_table(records, "opportunities_need"), "discipline_id": records.discipline.pk},
    )
    assert Need.objects.get(pk=first).discipline_id is None
    assert Need.objects.get(pk=second).discipline_id == records.discipline.pk
    assert Need.objects.filter(opportunity=records.opportunity).count() == 2


@pytest.mark.parametrize("kind", ["email", "phone", "whatsapp", "telegram"])
def test_public_contact_accepts_declared_external_channel(records, kind):
    identifier = insert_row("opportunities_contact", {**contact_values(records), "kind": kind})
    assert OpportunityContact.objects.get(pk=identifier).kind == kind


def test_public_contacts_remain_independent_of_hidden_profile_contacts(records):
    profile = Profile.objects.create(account=records.owner, full_name="Persona sintética")
    private = Contact.objects.create(
        profile=profile, kind="email", value="privado-sintetico@example.org", is_visible=False
    )
    public = OpportunityContact.objects.create(
        opportunity=records.opportunity, kind="email", value="publico-sintetico@example.org"
    )
    private.value = "privado-cambiado@example.org"
    private.save(update_fields={"value"})
    public.refresh_from_db()
    assert public.value == "publico-sintetico@example.org"
    private.delete()
    assert OpportunityContact.objects.filter(pk=public.pk).exists()


def test_funding_presence_is_single_source_without_boolean_and_can_be_removed(records):
    assert not Funding.objects.filter(opportunity=records.opportunity).exists()
    first = insert_row("opportunities_funding", funding_values(records))
    assert_rejected("opportunities_funding", funding_values(records), "opportunities_funding_pkey")
    Funding.objects.get(pk=first).delete()
    assert Opportunity.objects.filter(pk=records.opportunity.pk).exists()
    assert not Funding.objects.filter(opportunity=records.opportunity).exists()
    insert_row("opportunities_funding", funding_values(records))


def test_contact_and_history_unique_keys_allow_other_channels_and_revisions(records):
    insert_row("opportunities_contact", contact_values(records))
    assert_rejected("opportunities_contact", contact_values(records), "uq_t22_01")
    insert_row("opportunities_contact", {**contact_values(records), "kind": "telegram"})
    insert_row("opportunities_lifecycle_event", event_values(records))
    assert_rejected("opportunities_lifecycle_event", event_values(records), "uq_t19_key01")
    insert_row("opportunities_lifecycle_event", {**event_values(records), "validity_revision": 2})
    assert OpportunityContact.objects.count() == 2 and LifecycleEvent.objects.count() == 2


@pytest.mark.parametrize("table", SCHEMA)
def test_sql_defaults_and_uuid_string_do_not_expose_content(records, table):
    identifier = insert_row(table, values_for_table(records, table))
    row = MODELS[table].objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(row) == str(identifier)
    assert row.created_at.utcoffset().total_seconds() == 0
    if hasattr(row, "updated_at"):
        assert row.updated_at == row.created_at
    if table == "opportunities_opportunity":
        assert (row.lifecycle, row.visibility, row.row_version, row.validity_revision) == (
            "draft",
            "visible",
            1,
            0,
        )
        assert row.published_at is None and row.expires_at is None
    if table in ("opportunities_need", "opportunities_contact"):
        assert row.sort_order == 0


@pytest.mark.parametrize(
    "table,field,new_value",
    [
        ("opportunities_opportunity", "title", "Título sintético editado"),
        ("opportunities_need", "description", "Necesidad sintética editada"),
        ("opportunities_funding", "estimated_amount", Decimal("2.00")),
        ("opportunities_contact", "label", "Etiqueta sintética"),
    ],
)
def test_partial_orm_save_updates_timestamp_without_changing_creation(
    records, table, field, new_value
):
    identifier = insert_row(
        table, {**values_for_table(records, table), "created_at": START, "updated_at": START}
    )
    row = MODELS[table].objects.get(pk=identifier)
    setattr(row, field, new_value)
    row.save(update_fields={field})
    row.refresh_from_db()
    assert row.created_at == START and row.updated_at > START
    assert getattr(row, field) == new_value


def values_for_reference(records, table, field):
    values = values_for_table(records, table)
    if field == "owner_organization_id":
        values.pop("owner_account_id")
    return values


@pytest.mark.parametrize("table,field,constraint,target", REFERENCES)
def test_missing_foreign_target_is_rejected(records, table, field, constraint, target):
    assert_rejected(
        table, {**values_for_reference(records, table, field), field: uuid4()}, constraint
    )


@pytest.mark.parametrize("table,field,constraint,target_table", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_nine_references_restrict_deletion_without_cascade(
    records, table, field, constraint, target_table, via_orm
):
    target = {
        "identity_account": records.free,
        "organizations_organization": records.organization,
        "opportunities_opportunity": records.opportunity,
        "academics_discipline": records.discipline,
    }[target_table]
    identifier = insert_row(
        table, {**values_for_reference(records, table, field), field: target.pk}
    )
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
        and MODELS[table].objects.filter(pk=identifier).exists()
    )


def test_revoked_representative_does_not_erase_organization_opportunity(records):
    identifier = insert_row("opportunities_opportunity", opportunity_values(records, True))
    representation = Representation.objects.create(
        organization=records.organization,
        account=records.author,
        granted_by=records.owner,
        created_at=START,
    )
    representation.revoked_at = END
    representation.revoked_by = records.owner
    representation.save(update_fields={"revoked_at", "revoked_by"})
    opportunity = Opportunity.objects.get(pk=identifier)
    assert (
        opportunity.owner_organization_id == records.organization.pk
        and opportunity.author_id == records.author.pk
    )
    assert Representation.objects.filter(pk=representation.pk, revoked_at=END).exists()


def test_outer_failure_rolls_back_full_opportunity_aggregate(records):
    before = {table: model.objects.count() for table, model in MODELS.items()}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            identifier = insert_row("opportunities_opportunity", opportunity_values(records))
            for table in SCHEMA:
                if table != "opportunities_opportunity":
                    insert_row(
                        table, {**values_for_table(records, table), "opportunity_id": identifier}
                    )
            raise RuntimeError("fallo sintético de coordinación")
    assert {table: model.objects.count() for table, model in MODELS.items()} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "table,constraint",
    [
        ("opportunities_funding", "opportunities_funding_pkey"),
        ("opportunities_contact", "uq_t22_01"),
        ("opportunities_lifecycle_event", "uq_t19_key01"),
    ],
)
def test_concurrent_inserts_preserve_single_funding_contact_and_revision(
    records, table, constraint
):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    values = values_for_table(records, table)
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
    assert MODELS[table].objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_opportunities_migration_reverses_and_restores_graph_preserving_owners():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion-oportunidades@example.org")
    organization = Organization.objects.create(
        name="Entidad sintética conservada", kind="other", created_by=account
    )
    discipline = Discipline.objects.create(
        name="Disciplina sintética conservada", origin="declared"
    )
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("opportunities", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert (
            Account.objects.filter(pk=account.pk).exists()
            and Organization.objects.filter(pk=organization.pk).exists()
        )
        assert Discipline.objects.filter(pk=discipline.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables and not MigrationExecutor(
        connection
    ).migration_plan(targets)
    test_nine_restrict_foreign_keys_have_exact_names_and_targets()
    test_indexes_preserve_expiry_filter_sort_expression_and_unique_keys()
    assert (
        Account.objects.filter(pk=account.pk).exists()
        and Organization.objects.filter(pk=organization.pk).exists()
    )
