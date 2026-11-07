"""T23–T25: relaciones, eventos y destacados con datos sintéticos en PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.access.models import Capability, Grant
from modules.identity.models import Account
from modules.opportunities.models import Opportunity
from modules.organizations.models import Organization, Representation
from modules.profiles.models import Contact, Profile
from modules.publications.models import EventDetail, Highlight, Publication

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=1)
EVENT_DATE = date(2026, 1, 15)
# Las constantes de esquema se fijan durante la implementación, sin leer la tesis al ejecutar.
SCHEMA = {
    "publications_publication": {
        "id": ("uuid", False),
        "owner_account_id": ("uuid", True),
        "owner_organization_id": ("uuid", True),
        "author_id": ("uuid", False),
        "kind": ("character varying(16)", False),
        "title": ("character varying(200)", False),
        "body": ("text", False),
        "status": ("character varying(16)", False),
        "visibility": ("character varying(16)", False),
        "published_at": ("timestamp with time zone", True),
        "row_version": ("integer", False),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "publications_event_detail": {
        "publication_id": ("uuid", False),
        "publication_kind": ("character varying(16)", False),
        "event_date": ("date", False),
        "start_time": ("time without time zone", True),
        "time_zone": ("character varying(64)", False),
        "mode": ("character varying(16)", False),
        "venue": ("text", True),
        "participation_url": ("text", True),
        "contact_kind": ("character varying(16)", True),
        "contact_value": ("text", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "publications_highlight": {
        "id": ("uuid", False),
        "opportunity_id": ("uuid", True),
        "publication_id": ("uuid", True),
        "granted_by": ("uuid", False),
        "source_grant_id": ("uuid", True),
        "starts_at": ("timestamp with time zone", False),
        "ends_at": ("timestamp with time zone", True),
        "revoked_at": ("timestamp with time zone", True),
        "revoked_by": ("uuid", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
}
REFERENCES = [
    ("publications_publication", ("owner_account_id",), "fk_t23_01", "identity_account", ("id",)),
    (
        "publications_publication",
        ("owner_organization_id",),
        "fk_t23_02",
        "organizations_organization",
        ("id",),
    ),
    ("publications_publication", ("author_id",), "fk_t23_03", "identity_account", ("id",)),
    (
        "publications_event_detail",
        ("publication_id", "publication_kind"),
        "fk_t24_01",
        "publications_publication",
        ("id", "kind"),
    ),
    (
        "publications_highlight",
        ("opportunity_id",),
        "fk_t25_01",
        "opportunities_opportunity",
        ("id",),
    ),
    (
        "publications_highlight",
        ("publication_id",),
        "fk_t25_02",
        "publications_publication",
        ("id",),
    ),
    ("publications_highlight", ("granted_by",), "fk_t25_03", "identity_account", ("id",)),
    ("publications_highlight", ("source_grant_id",), "fk_t25_04", "access_grant", ("id",)),
    ("publications_highlight", ("revoked_by",), "fk_t25_05", "identity_account", ("id",)),
]
MODELS = {
    "publications_publication": Publication,
    "publications_event_detail": EventDetail,
    "publications_highlight": Highlight,
}


def insert_row(table, values):
    pk = "publication_id" if table == "publications_event_detail" else "id"
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


def publication_values(records, kind="news", organizational=False):
    return {
        "owner_organization_id" if organizational else "owner_account_id": records.organization.pk
        if organizational
        else records.owner.pk,
        "author_id": records.author.pk,
        "kind": kind,
        "title": "Divulgación sintética",
        "body": "Avances sintéticos para compartir",
    }


def detail_values(records):
    return {
        "publication_id": records.event.pk,
        "event_date": EVENT_DATE,
        "mode": "online",
        "participation_url": "https://example.org/evento-sintetico",
    }


def highlight_values(records, target="publication"):
    return {
        target + "_id": records.news.pk if target == "publication" else records.opportunity.pk,
        "granted_by": records.author.pk,
    }


def values_for_table(records, table):
    if table == "publications_publication":
        return publication_values(records)
    if table == "publications_event_detail":
        return detail_values(records)
    return highlight_values(records)


@pytest.fixture
def records():
    owner, author, free = [
        Account.objects.create_user(f"divulgacion-{name}@example.org")
        for name in ("titular", "autor", "libre")
    ]
    organization = Organization.objects.create(
        name="Entidad sintética de divulgación", kind="other", created_by=owner
    )
    capability = Capability.objects.create(
        code="synthetic.highlight", description="Capacidad sintética de prueba"
    )
    grant = Grant.objects.create(
        account=author,
        capability=capability,
        scope_kind="global",
        granted_by=owner,
        source="administrative",
        valid_from=START,
    )
    opportunity = Opportunity.objects.create(
        owner_account=owner,
        author=author,
        title="Oportunidad sintética",
        description="Colaboración sintética",
        area="Área sintética",
        responsible_label="Responsable sintético",
    )
    records = SimpleNamespace(
        owner=owner,
        author=author,
        free=free,
        organization=organization,
        grant=grant,
        opportunity=opportunity,
    )
    records.news = Publication.objects.create(**publication_values(records))
    records.event = Publication.objects.create(**publication_values(records, "event"))
    return records


@pytest.mark.parametrize(
    "table,number,count",
    [
        ("publications_publication", 23, 8),
        ("publications_event_detail", 24, 9),
        ("publications_highlight", 25, 3),
    ],
)
def test_thirty_six_columns_and_twenty_checks_match_design(table, number, count):
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


def test_nine_named_foreign_keys_include_only_compound_event_reference():
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
    assert not EventDetail._meta.get_field("publication").db_constraint


def test_indexes_keep_typed_key_order_and_open_target_uniqueness():
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
    ordinary = (
        {f"ix_t23_{n:02}" for n in range(1, 5)}
        | {"ix_t24_01"}
        | {f"ix_t25_{n:02}" for n in range(3, 8)}
    )
    assert set(indexes) == ordinary | {"uq_t23_key01", "uq_t25_01", "uq_t25_02"}
    assert "published_at DESC, id" in indexes["ix_t23_01"][0]
    assert "publication_id, publication_kind" in indexes["ix_t24_01"][0]
    for name, field in [("uq_t25_01", "opportunity_id"), ("uq_t25_02", "publication_id")]:
        definition, predicate, unique = indexes[name]
        assert (
            unique
            and f"({field})" in definition
            and "revoked_at IS NULL" in predicate
            and f"{field} IS NOT NULL" in predicate
        )
    assert all(indexes[name][1] is None and not indexes[name][2] for name in ordinary)
    assert constraints["publications_publication"]["uq_t23_key01"]["columns"] == ["id", "kind"]
    assert constraints["publications_event_detail"]["publications_event_detail_pkey"][
        "columns"
    ] == ["publication_id"]


@pytest.mark.parametrize("organizational", [False, True])
@pytest.mark.parametrize("kind", ["news", "event"])
def test_publication_owner_is_exclusive_and_separate_from_author(records, organizational, kind):
    identifier = insert_row(
        "publications_publication", publication_values(records, kind, organizational)
    )
    row = Publication.objects.get(pk=identifier)
    assert row.author_id == records.author.pk and row.kind == kind
    assert row.owner_account_id == (None if organizational else records.owner.pk)
    assert row.owner_organization_id == (records.organization.pk if organizational else None)


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"owner_account_id": None}, "ck_t23_01"),
        ({"owner_organization_id": "organization"}, "ck_t23_01"),
        ({"kind": "invalid"}, "ck_t23_02"),
        ({"status": "invalid"}, "ck_t23_03"),
        ({"visibility": "invalid"}, "ck_t23_04"),
        ({"title": ""}, "ck_t23_05"),
        ({"title": "   "}, "ck_t23_05"),
        ({"body": ""}, "ck_t23_06"),
        ({"body": "   "}, "ck_t23_06"),
        ({"status": "published"}, "ck_t23_07"),
        ({"status": "withdrawn"}, "ck_t23_07"),
        ({"row_version": 0}, "ck_t23_08"),
        ({"row_version": -1}, "ck_t23_08"),
    ],
)
def test_publication_checks_reject_direct_sql(records, changes, constraint):
    if changes.get("owner_organization_id") == "organization":
        changes = {**changes, "owner_organization_id": records.organization.pk}
    assert_rejected(
        "publications_publication", {**publication_values(records), **changes}, constraint
    )


@pytest.mark.parametrize("status", ["published", "withdrawn"])
@pytest.mark.parametrize("visibility", ["visible", "hidden", "removed"])
def test_editorial_status_and_moderation_visibility_preserve_publication_date(
    records, status, visibility
):
    identifier = insert_row(
        "publications_publication",
        {
            **publication_values(records),
            "status": status,
            "visibility": visibility,
            "published_at": START,
        },
    )
    row = Publication.objects.get(pk=identifier)
    assert (row.status, row.visibility, row.published_at) == (status, visibility, START)


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"publication_kind": "news"}, "ck_t24_01"),
        ({"contact_kind": "email"}, "ck_t24_02"),
        ({"contact_value": "publico@example.org"}, "ck_t24_02"),
        ({"participation_url": None}, "ck_t24_03"),
        ({"mode": "invalid"}, "ck_t24_04"),
        ({"contact_kind": "invalid", "contact_value": "texto-sintetico"}, "ck_t24_05"),
        ({"venue": ""}, "ck_t24_06"),
        ({"venue": "   "}, "ck_t24_06"),
        (
            {
                "participation_url": "",
                "contact_kind": "email",
                "contact_value": "publico@example.org",
            },
            "ck_t24_07",
        ),
        (
            {
                "participation_url": "   ",
                "contact_kind": "email",
                "contact_value": "publico@example.org",
            },
            "ck_t24_07",
        ),
        ({"contact_kind": "email", "contact_value": ""}, "ck_t24_08"),
        ({"contact_kind": "email", "contact_value": "   "}, "ck_t24_08"),
        ({"time_zone": ""}, "ck_t24_09"),
        ({"time_zone": "   "}, "ck_t24_09"),
    ],
)
def test_event_details_require_coherent_public_participation_data(records, changes, constraint):
    assert_rejected("publications_event_detail", {**detail_values(records), **changes}, constraint)


@pytest.mark.parametrize("mode", ["in_person", "online", "hybrid"])
@pytest.mark.parametrize("route", ["url", "contact", "both"])
def test_event_modes_accept_external_url_contact_or_both_without_inventing_time(
    records, mode, route
):
    values = {
        **detail_values(records),
        "mode": mode,
        "participation_url": None if route == "contact" else "https://example.org/evento",
    }
    if route != "url":
        values.update(contact_kind="email", contact_value="publico@example.org")
    identifier = insert_row("publications_event_detail", values)
    detail = EventDetail.objects.get(pk=identifier)
    assert detail.start_time is None and detail.event_date == EVENT_DATE and detail.venue is None
    assert detail.time_zone == "America/Havana" and detail.publication_kind == "event"


@pytest.mark.parametrize("kind", ["email", "phone", "whatsapp", "telegram"])
def test_event_contact_channels_and_optional_local_time_are_preserved(records, kind):
    identifier = insert_row(
        "publications_event_detail",
        {
            **detail_values(records),
            "start_time": time(14, 30),
            "time_zone": "Etc/UTC",
            "contact_kind": kind,
            "contact_value": "contacto-sintetico",
            "venue": "Sede sintética",
        },
    )
    detail = EventDetail.objects.get(pk=identifier)
    assert (detail.start_time, detail.time_zone, detail.contact_kind) == (
        time(14, 30),
        "Etc/UTC",
        kind,
    )


def test_compound_foreign_key_blocks_news_target_and_parent_type_mutation(records):
    assert_rejected(
        "publications_event_detail",
        {**detail_values(records), "publication_id": records.news.pk},
        "fk_t24_01",
    )
    insert_row("publications_event_detail", detail_values(records))
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Publication.objects.filter(pk=records.event.pk).update(kind="news")
    assert error.value.__cause__.diag.constraint_name == "fk_t24_01"
    records.event.refresh_from_db()
    assert records.event.kind == "event"
    assert_rejected(
        "publications_event_detail", detail_values(records), "publications_event_detail_pkey"
    )


def test_detail_reassignment_to_news_fails_and_other_event_is_allowed(records):
    identifier = insert_row("publications_event_detail", detail_values(records))
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE publications_event_detail SET publication_id=%s WHERE publication_id=%s",
                    [records.news.pk, identifier],
                )
    assert error.value.__cause__.diag.constraint_name == "fk_t24_01"
    other = Publication.objects.create(**publication_values(records, "event"))
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE publications_event_detail SET publication_id=%s WHERE publication_id=%s",
            [other.pk, identifier],
        )
    assert EventDetail.objects.get(pk=other.pk).publication_kind == "event"


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"publication_id": None}, "ck_t25_01"),
        ({"opportunity_id": "opportunity"}, "ck_t25_01"),
        ({"starts_at": START, "ends_at": START}, "ck_t25_02"),
        ({"starts_at": END, "ends_at": START}, "ck_t25_02"),
        ({"revoked_at": END}, "ck_t25_03"),
        ({"revoked_by": "free"}, "ck_t25_03"),
    ],
)
def test_highlight_target_period_and_revocation_checks(records, changes, constraint):
    changes = {
        key: getattr(records, value).pk
        if key in ("opportunity_id", "revoked_by") and isinstance(value, str)
        else value
        for key, value in changes.items()
    }
    assert_rejected("publications_highlight", {**highlight_values(records), **changes}, constraint)


@pytest.mark.parametrize(
    "target,constraint", [("opportunity", "uq_t25_01"), ("publication", "uq_t25_02")]
)
def test_expired_unrevoked_highlight_keeps_slot_until_closed_and_history_survives(
    records, target, constraint
):
    identifier = insert_row(
        "publications_highlight",
        {**highlight_values(records, target), "starts_at": START, "ends_at": END},
    )
    assert_rejected("publications_highlight", highlight_values(records, target), constraint)
    Highlight.objects.filter(pk=identifier).update(revoked_at=END, revoked_by=records.author)
    replacement = insert_row("publications_highlight", highlight_values(records, target))
    assert replacement != identifier and Highlight.objects.count() == 2
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Highlight.objects.filter(pk=identifier).update(revoked_at=None, revoked_by=None)
    assert error.value.__cause__.diag.constraint_name == constraint


def test_distinct_highlight_targets_and_types_do_not_conflict(records):
    insert_row("publications_highlight", highlight_values(records))
    insert_row("publications_highlight", highlight_values(records, "opportunity"))
    insert_row(
        "publications_highlight", {**highlight_values(records), "publication_id": records.event.pk}
    )
    assert Highlight.objects.count() == 3


@pytest.mark.parametrize("with_source", [False, True])
def test_highlight_keeps_optional_source_without_implying_authority(records, with_source):
    identifier = insert_row(
        "publications_highlight",
        {**highlight_values(records), "source_grant_id": records.grant.pk if with_source else None},
    )
    row = Highlight.objects.get(pk=identifier)
    assert row.ends_at is None and row.revoked_at is None and row.revoked_by_id is None
    assert row.source_grant_id == (records.grant.pk if with_source else None)


@pytest.mark.parametrize("table", SCHEMA)
def test_sql_defaults_and_uuid_only_string(records, table):
    identifier = insert_row(table, values_for_table(records, table))
    row = MODELS[table].objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(row) == str(identifier)
    assert row.created_at == row.updated_at and row.created_at.utcoffset().total_seconds() == 0
    if table == "publications_publication":
        assert (row.status, row.visibility, row.row_version, row.published_at) == (
            "draft",
            "visible",
            1,
            None,
        )
    if table == "publications_highlight":
        assert row.starts_at == row.created_at


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("publications_publication", "title", "Título sintético nuevo"),
        ("publications_event_detail", "venue", "Sede sintética nueva"),
        ("publications_highlight", "ends_at", END),
    ],
)
def test_partial_save_updates_timestamp_and_keeps_creation(records, table, field, value):
    values = {**values_for_table(records, table), "created_at": START, "updated_at": START}
    if table == "publications_highlight":
        values["starts_at"] = START
    identifier = insert_row(table, values)
    row = MODELS[table].objects.get(pk=identifier)
    setattr(row, field, value)
    row.save(update_fields={field})
    row.refresh_from_db()
    assert row.created_at == START and row.updated_at > START and getattr(row, field) == value


def values_for_reference(records, table, fields, target_id):
    values = values_for_table(records, table)
    field = fields[0]
    if table == "publications_publication" and field == "owner_organization_id":
        values.pop("owner_account_id")
    if table == "publications_highlight" and field == "opportunity_id":
        values.pop("publication_id")
    if field == "revoked_by":
        values["revoked_at"] = END
    values[field] = target_id
    return values


@pytest.mark.parametrize("table,fields,constraint,target,keys", REFERENCES)
def test_missing_foreign_references_are_rejected(records, table, fields, constraint, target, keys):
    from uuid import uuid4

    assert_rejected(table, values_for_reference(records, table, fields, uuid4()), constraint)


@pytest.mark.parametrize("table,fields,constraint,target_table,keys", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_all_references_restrict_sql_and_orm_deletion(
    records, table, fields, constraint, target_table, keys, via_orm
):
    target = {
        "identity_account": records.free,
        "organizations_organization": records.organization,
        "publications_publication": records.event,
        "opportunities_opportunity": records.opportunity,
        "access_grant": records.grant,
    }[target_table]
    identifier = insert_row(table, values_for_reference(records, table, fields, target.pk))
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


def test_event_contact_is_independent_of_private_profile_contact(records):
    profile = Profile.objects.create(account=records.owner, full_name="Persona sintética")
    private = Contact.objects.create(
        profile=profile, kind="email", value="privado@example.org", is_visible=False
    )
    identifier = insert_row(
        "publications_event_detail",
        {**detail_values(records), "contact_kind": "email", "contact_value": "publico@example.org"},
    )
    private.delete()
    assert EventDetail.objects.get(pk=identifier).contact_value == "publico@example.org"


def test_representative_revocation_keeps_organization_publication_and_author(records):
    identifier = insert_row(
        "publications_publication", publication_values(records, organizational=True)
    )
    representation = Representation.objects.create(
        organization=records.organization,
        account=records.author,
        granted_by=records.owner,
        created_at=START,
    )
    representation.revoked_at = END
    representation.revoked_by = records.owner
    representation.save(update_fields={"revoked_at", "revoked_by"})
    row = Publication.objects.get(pk=identifier)
    assert (
        row.owner_organization_id == records.organization.pk and row.author_id == records.author.pk
    )


def test_outer_transaction_rolls_back_publication_event_and_highlight(records):
    before = {table: model.objects.count() for table, model in MODELS.items()}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            identifier = insert_row(
                "publications_publication", publication_values(records, "event")
            )
            insert_row(
                "publications_event_detail",
                {**detail_values(records), "publication_id": identifier},
            )
            insert_row(
                "publications_highlight",
                {**highlight_values(records), "publication_id": identifier},
            )
            raise RuntimeError("fallo sintético de coordinación")
    assert {table: model.objects.count() for table, model in MODELS.items()} == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "target,constraint", [("opportunity", "uq_t25_01"), ("publication", "uq_t25_02")]
)
def test_concurrent_highlights_cannot_duplicate_unrevoked_target(records, target, constraint):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    values = highlight_values(records, target)
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
                identifier = insert_row("publications_highlight", values)
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
    assert Highlight.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_migration_reverses_and_restores_composite_reference_preserving_other_modules(records):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("publications", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert (
            Account.objects.filter(pk=records.owner.pk).exists()
            and Opportunity.objects.filter(pk=records.opportunity.pk).exists()
        )
        assert (
            Organization.objects.filter(pk=records.organization.pk).exists()
            and Grant.objects.filter(pk=records.grant.pk).exists()
        )
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables and not MigrationExecutor(
        connection
    ).migration_plan(targets)
    test_nine_named_foreign_keys_include_only_compound_event_reference()
    test_indexes_keep_typed_key_order_and_open_target_uniqueness()
