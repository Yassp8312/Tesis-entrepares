"""T34–T36: referencias, intención única e intentos con datos sintéticos; sin adaptador."""

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
from psycopg.types.json import Jsonb

from modules.identity.models import Account, EmailChallenge
from modules.notifications.models import DeliveryAttempt, Notice, OutboxMessage
from modules.opportunities.models import LifecycleEvent, Opportunity

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=1)
SCHEMA = {
    "notifications_notice": {
        "id": ("uuid", False),
        "opportunity_id": ("uuid", False),
        "validity_revision": ("integer", False),
        "kind": ("character varying(32)", False),
        "scheduled_for": ("timestamp with time zone", False),
        "channel": ("character varying(32)", True),
        "cancelled_at": ("timestamp with time zone", True),
        "cancellation_reason": ("text", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "notifications_outbox": {
        "id": ("uuid", False),
        "notice_id": ("uuid", True),
        "challenge_id": ("uuid", True),
        "recipient_account_id": ("uuid", True),
        "channel": ("character varying(32)", False),
        "destination": ("text", False),
        "template_key": ("character varying(80)", False),
        "payload": ("jsonb", False),
        "idempotency_key": ("character varying(160)", False),
        "status": ("character varying(16)", False),
        "available_at": ("timestamp with time zone", False),
        "lease_until": ("timestamp with time zone", True),
        "sent_at": ("timestamp with time zone", True),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
    },
    "notifications_delivery_attempt": {
        "id": ("uuid", False),
        "outbox_id": ("uuid", False),
        "attempt_no": ("integer", False),
        "started_at": ("timestamp with time zone", False),
        "finished_at": ("timestamp with time zone", True),
        "result": ("character varying(16)", False),
        "provider_reference": ("text", True),
        "error_code": ("character varying(80)", True),
    },
}
REFERENCES = [
    (
        "notifications_notice",
        ("opportunity_id", "validity_revision"),
        "fk_t34_01",
        "opportunities_lifecycle_event",
        ("opportunity_id", "validity_revision"),
    ),
    ("notifications_outbox", ("notice_id",), "fk_t35_01", "notifications_notice", ("id",)),
    ("notifications_outbox", ("challenge_id",), "fk_t35_02", "identity_email_challenge", ("id",)),
    ("notifications_outbox", ("recipient_account_id",), "fk_t35_03", "identity_account", ("id",)),
    (
        "notifications_delivery_attempt",
        ("outbox_id",),
        "fk_t36_01",
        "notifications_outbox",
        ("id",),
    ),
]
MODELS = {
    "notifications_notice": Notice,
    "notifications_outbox": OutboxMessage,
    "notifications_delivery_attempt": DeliveryAttempt,
}


def insert_row(table, values):
    values = {
        key: Jsonb(value)
        if key == "payload" and value is not None and not isinstance(value, Jsonb)
        else value
        for key, value in values.items()
    }
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


def notice_values(r):
    return {"opportunity_id": r.opportunity.pk, "validity_revision": 1, "scheduled_for": START}


def outbox_values(r, challenge=False):
    return {
        "challenge_id" if challenge else "notice_id": r.challenge.pk if challenge else r.notice.pk,
        "channel": "synthetic",
        "destination": "destino-sintetico@example.org",
        "template_key": "synthetic.template",
        "idempotency_key": "synthetic.message",
    }


def attempt_values(r):
    return {"outbox_id": r.outbox.pk, "attempt_no": 1}


def values_for_table(r, table):
    return {
        "notifications_notice": notice_values,
        "notifications_outbox": outbox_values,
        "notifications_delivery_attempt": attempt_values,
    }[table](r)


def make_opportunity(account):
    return Opportunity.objects.create(
        owner_account=account,
        author=account,
        title="Oportunidad sintética",
        description="Necesidad sintética",
        area="Área sintética",
        responsible_label="Responsable sintético",
    )


def make_event(opportunity, account, revision):
    return LifecycleEvent.objects.create(
        opportunity=opportunity,
        validity_revision=revision,
        event_kind="publish" if revision == 1 else "extend",
        actor=account,
        from_state="draft" if revision == 1 else "active",
        to_state="active",
        new_expires_at=END,
    )


@pytest.fixture
def records():
    account = Account.objects.create_user("avisos-cuenta@example.org")
    free = Account.objects.create_user("avisos-libre@example.org")
    opportunity = make_opportunity(account)
    other_opportunity = make_opportunity(account)
    event = make_event(opportunity, account, 1)
    make_event(opportunity, account, 2)
    other_event = make_event(other_opportunity, account, 1)
    challenge = EmailChallenge.objects.create(
        account=account,
        purpose="email_confirmation",
        email_snapshot="comprobacion-sintetica@example.org",
        created_at=START,
        expires_at=END,
    )
    r = SimpleNamespace(
        account=account,
        free=free,
        opportunity=opportunity,
        other_opportunity=other_opportunity,
        event=event,
        other_event=other_event,
        challenge=challenge,
    )
    r.notice = Notice.objects.create(**notice_values(r), channel="fixture")
    r.outbox = OutboxMessage.objects.create(
        **{**outbox_values(r), "idempotency_key": "synthetic.base"}
    )
    return r


@pytest.mark.parametrize(
    "table,number,count",
    [
        ("notifications_notice", 34, 2),
        ("notifications_outbox", 35, 9),
        ("notifications_delivery_attempt", 36, 4),
    ],
)
def test_thirty_three_columns_and_fifteen_checks_match_design(table, number, count):
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


def test_five_named_restrict_references_include_lifecycle_revision():
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
    assert not Notice._meta.get_field("opportunity").db_constraint


def test_indexes_preserve_null_channel_uniqueness_and_dispatch_predicates():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,pg_get_indexdef(i.indexrelid),pg_get_expr(i.indpred,i.indrelid),i.indisunique,i.indnullsnotdistinct FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=ANY(%s::regclass[]) AND NOT i.indisprimary",
            [list(SCHEMA)],
        )
        indexes = {
            name: (definition, predicate, unique, nulls)
            for name, definition, predicate, unique, nulls in cursor
        }
        constraints = {
            table: connection.introspection.get_constraints(cursor, table) for table in SCHEMA
        }
    assert set(indexes) == {"uq_t34_01", "ix_t34_02", "uq_t35_key01", "uq_t36_key01"} | {
        f"ix_t35_{n:02}" for n in range(1, 6)
    }
    assert indexes["uq_t34_01"][2:] == (True, True)
    assert constraints["notifications_notice"]["uq_t34_01"]["columns"] == [
        "opportunity_id",
        "validity_revision",
        "kind",
        "channel",
    ]
    assert constraints["notifications_outbox"]["uq_t35_key01"]["columns"] == ["idempotency_key"]
    assert constraints["notifications_delivery_attempt"]["uq_t36_key01"]["columns"] == [
        "outbox_id",
        "attempt_no",
    ]
    assert "cancelled_at IS NULL" in indexes["ix_t34_02"][1]
    assert "pending" in indexes["ix_t35_01"][1] and "failed" in indexes["ix_t35_01"][1]
    assert "processing" in indexes["ix_t35_02"][1]
    assert {name for name, (_, pred, _, _) in indexes.items() if pred is not None} == {
        "ix_t34_02",
        "ix_t35_01",
        "ix_t35_02",
    }


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"kind": "invalid"}, "ck_t34_01"),
        ({"validity_revision": 0}, "ck_t34_02"),
        ({"validity_revision": -1}, "ck_t34_02"),
    ],
)
def test_notice_checks(records, changes, constraint):
    assert_rejected("notifications_notice", {**notice_values(records), **changes}, constraint)


def test_compound_notice_reference_rejects_nonexistent_and_wrong_opportunity_revision(records):
    assert_rejected(
        "notifications_notice", {**notice_values(records), "validity_revision": 3}, "fk_t34_01"
    )
    assert_rejected(
        "notifications_notice",
        {
            **notice_values(records),
            "opportunity_id": records.other_opportunity.pk,
            "validity_revision": 2,
        },
        "fk_t34_01",
    )
    unused_opportunity = make_opportunity(records.account)
    for changes in ({"validity_revision": 3}, {"opportunity": unused_opportunity}):
        with pytest.raises(IntegrityError) as error:
            with transaction.atomic():
                LifecycleEvent.objects.filter(pk=records.event.pk).update(**changes)
        assert error.value.__cause__.diag.constraint_name == "fk_t34_01"


@pytest.mark.parametrize("channel", [None, "email"])
def test_notice_unique_slot_remains_occupied_when_cancelled(records, channel):
    values = {**notice_values(records), "channel": channel}
    identifier = insert_row("notifications_notice", values)
    assert_rejected("notifications_notice", values, "uq_t34_01")
    Notice.objects.filter(pk=identifier).update(
        cancelled_at=END, cancellation_reason="Cancelación sintética"
    )
    assert_rejected("notifications_notice", values, "uq_t34_01")
    insert_row("notifications_notice", {**values, "validity_revision": 2})


def test_distinct_notice_channels_and_revisions_are_independent(records):
    for channel in (None, "email", "synthetic-other"):
        insert_row("notifications_notice", {**notice_values(records), "channel": channel})
    assert Notice.objects.filter(opportunity=records.opportunity).count() == 4


def test_notice_without_channel_does_not_create_delivery_message(records):
    identifier = insert_row("notifications_notice", notice_values(records))
    assert Notice.objects.get(pk=identifier).channel is None
    assert not OutboxMessage.objects.filter(notice_id=identifier).exists()


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"notice_id": None}, "ck_t35_01"),
        ({"challenge_id": "challenge"}, "ck_t35_01"),
        ({"status": "processing"}, "ck_t35_03"),
        ({"status": "sent"}, "ck_t35_04"),
        ({"sent_at": END}, "ck_t35_04"),
        ({"status": "invalid"}, "ck_t35_05"),
        ({"channel": ""}, "ck_t35_06"),
        ({"channel": "   "}, "ck_t35_06"),
        ({"destination": ""}, "ck_t35_07"),
        ({"destination": "   "}, "ck_t35_07"),
        ({"template_key": ""}, "ck_t35_08"),
        ({"template_key": "   "}, "ck_t35_08"),
        ({"idempotency_key": ""}, "ck_t35_09"),
        ({"idempotency_key": "   "}, "ck_t35_09"),
    ],
)
def test_outbox_checks_reject_incoherent_intentions(records, changes, constraint):
    if changes.get("challenge_id") == "challenge":
        changes = {**changes, "challenge_id": records.challenge.pk}
    assert_rejected("notifications_outbox", {**outbox_values(records), **changes}, constraint)


@pytest.mark.parametrize("payload", [[], True, "texto-sintetico", 42, Jsonb(None)])
def test_payload_requires_json_object_including_explicit_json_null_rejection(records, payload):
    assert_rejected(
        "notifications_outbox", {**outbox_values(records), "payload": payload}, "ck_t35_02"
    )


def test_payload_cannot_be_sql_null(records):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            insert_row("notifications_outbox", {**outbox_values(records), "payload": None})
    assert error.value.__cause__.diag.column_name == "payload"


@pytest.mark.parametrize("challenge", [False, True])
def test_each_exclusive_origin_and_optional_account_are_preserved(records, challenge):
    identifier = insert_row(
        "notifications_outbox",
        {
            **outbox_values(records, challenge),
            "recipient_account_id": records.account.pk if challenge else None,
        },
    )
    row = OutboxMessage.objects.get(pk=identifier)
    assert row.notice_id == (None if challenge else records.notice.pk)
    assert row.challenge_id == (records.challenge.pk if challenge else None)
    assert row.destination == "destino-sintetico@example.org"


@pytest.mark.parametrize("status", ["pending", "processing", "sent", "failed", "cancelled"])
def test_outbox_states_keep_required_lease_and_send_timestamp(records, status):
    identifier = insert_row(
        "notifications_outbox",
        {
            **outbox_values(records),
            "status": status,
            "lease_until": END if status == "processing" else None,
            "sent_at": END if status == "sent" else None,
        },
    )
    assert OutboxMessage.objects.get(pk=identifier).status == status


def test_idempotency_is_global_across_origin_channel_and_destination(records):
    insert_row("notifications_outbox", outbox_values(records))
    assert_rejected(
        "notifications_outbox",
        {
            **outbox_values(records, True),
            "channel": "another",
            "destination": "otro-sintetico@example.org",
        },
        "uq_t35_key01",
    )


def test_default_payload_objects_are_not_shared_between_messages(records):
    first = OutboxMessage.objects.create(**outbox_values(records))
    second = OutboxMessage.objects.create(
        **{**outbox_values(records), "idempotency_key": "synthetic.second"}
    )
    first.payload["revision"] = 1
    first.save(update_fields={"payload"})
    second.refresh_from_db()
    assert second.payload == {} and first.payload == {"revision": 1}


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"result": "invalid"}, "ck_t36_01"),
        ({"attempt_no": 0}, "ck_t36_02"),
        ({"attempt_no": -1}, "ck_t36_02"),
        ({"started_at": END, "finished_at": START, "result": "failed"}, "ck_t36_03"),
        ({"finished_at": END}, "ck_t36_04"),
        ({"result": "accepted"}, "ck_t36_04"),
        ({"result": "failed"}, "ck_t36_04"),
        ({"result": "unknown"}, "ck_t36_04"),
    ],
)
def test_attempt_checks_preserve_number_and_completion_coherence(records, changes, constraint):
    assert_rejected(
        "notifications_delivery_attempt",
        {**attempt_values(records), "started_at": START, **changes},
        constraint,
    )


@pytest.mark.parametrize("result", ["accepted", "failed", "unknown"])
def test_finished_attempts_allow_equal_instants_and_observed_result(records, result):
    identifier = insert_row(
        "notifications_delivery_attempt",
        {
            **attempt_values(records),
            "started_at": START,
            "finished_at": START,
            "result": result,
            "provider_reference": "proveedor-sintetico",
            "error_code": "SYNTHETIC" if result == "failed" else None,
        },
    )
    row = DeliveryAttempt.objects.get(pk=identifier)
    assert row.finished_at == row.started_at == START and row.result == result
    records.outbox.refresh_from_db()
    assert records.outbox.status == "pending"


def test_attempt_numbers_are_unique_per_message(records):
    insert_row("notifications_delivery_attempt", attempt_values(records))
    assert_rejected("notifications_delivery_attempt", attempt_values(records), "uq_t36_key01")
    insert_row("notifications_delivery_attempt", {**attempt_values(records), "attempt_no": 2})
    assert DeliveryAttempt.objects.filter(outbox=records.outbox).count() == 2


@pytest.mark.parametrize("table", SCHEMA)
def test_sql_defaults_and_identifier_only_display(records, table):
    identifier = insert_row(table, values_for_table(records, table))
    row = MODELS[table].objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and str(row) == str(identifier)
    if table == "notifications_delivery_attempt":
        assert (
            row.result == "running"
            and row.finished_at is None
            and row.started_at.utcoffset().total_seconds() == 0
        )
    else:
        assert row.created_at == row.updated_at and row.created_at.utcoffset().total_seconds() == 0
    if table == "notifications_notice":
        assert row.kind == "expiry_reminder" and row.cancelled_at is None
    if table == "notifications_outbox":
        assert (
            row.payload == {}
            and row.status == "pending"
            and row.available_at == row.created_at
            and row.lease_until is None
            and row.sent_at is None
        )


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("notifications_notice", "cancellation_reason", "Nota sintética"),
        ("notifications_outbox", "destination", "editado-sintetico@example.org"),
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
    if table == "notifications_outbox" and fields[0] == "challenge_id":
        values.pop("notice_id")
    values[fields[0]] = target_id
    return values


@pytest.mark.parametrize("table,fields,constraint,target,keys", REFERENCES)
def test_missing_references_are_rejected(records, table, fields, constraint, target, keys):
    assert_rejected(table, values_for_reference(records, table, fields, uuid4()), constraint)


@pytest.mark.parametrize("table,fields,constraint,target_table,keys", REFERENCES)
@pytest.mark.parametrize("via_orm", [False, True])
def test_references_restrict_deletion_from_sql_and_orm(
    records, table, fields, constraint, target_table, keys, via_orm
):
    target = {
        "opportunities_lifecycle_event": records.other_event,
        "notifications_notice": records.notice,
        "identity_email_challenge": records.challenge,
        "identity_account": records.free,
        "notifications_outbox": records.outbox,
    }[target_table]
    values = values_for_reference(records, table, fields, target.pk)
    if table == "notifications_notice":
        values.update(
            opportunity_id=target.opportunity_id, validity_revision=target.validity_revision
        )
    identifier = insert_row(table, values)
    with pytest.raises(
        RestrictedError if via_orm and table != "notifications_notice" else IntegrityError
    ) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(target_table)),
                        [target.pk],
                    )
    if not via_orm or table == "notifications_notice":
        assert error.value.__cause__.diag.constraint_name == constraint
    assert (
        type(target).objects.filter(pk=target.pk).exists()
        and MODELS[table].objects.filter(pk=identifier).exists()
    )


def test_outer_transaction_rolls_back_business_change_notice_message_and_attempt(records):
    old_title = records.opportunity.title
    before = {table: model.objects.count() for table, model in MODELS.items()}
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            Opportunity.objects.filter(pk=records.opportunity.pk).update(title="Cambio sintético")
            notice = insert_row("notifications_notice", notice_values(records))
            message = insert_row(
                "notifications_outbox", {**outbox_values(records), "notice_id": notice}
            )
            insert_row(
                "notifications_delivery_attempt", {**attempt_values(records), "outbox_id": message}
            )
            raise RuntimeError("fallo sintético de coordinación")
    records.opportunity.refresh_from_db()
    assert (
        records.opportunity.title == old_title
        and {table: model.objects.count() for table, model in MODELS.items()} == before
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "scenario,constraint",
    [
        ("notice-null", "uq_t34_01"),
        ("notice-channel", "uq_t34_01"),
        ("outbox", "uq_t35_key01"),
        ("attempt", "uq_t36_key01"),
    ],
)
def test_concurrent_notices_intentions_and_attempts_do_not_duplicate(records, scenario, constraint):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    table = (
        "notifications_notice"
        if scenario.startswith("notice")
        else "notifications_outbox"
        if scenario == "outbox"
        else "notifications_delivery_attempt"
    )
    values = values_for_table(records, table)
    if scenario == "notice-channel":
        values["channel"] = "email"
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
    assert (
        sorted(result[0] for result in results) == ["created", "rejected"]
        and len({result[2] for result in results}) == 2
    )
    assert next(result[1] for result in results if result[0] == "rejected") == constraint


@pytest.mark.django_db(transaction=True)
def test_migration_reverses_and_restores_revision_reference_preserving_sources(records):
    assert connection.settings_dict["NAME"] == "test_entrepares"
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate([("notifications", None)])
        assert not (set(SCHEMA) & set(connection.introspection.table_names()))
        assert (
            Account.objects.filter(pk=records.account.pk).exists()
            and EmailChallenge.objects.filter(pk=records.challenge.pk).exists()
        )
        assert (
            LifecycleEvent.objects.filter(pk=records.event.pk).exists()
            and Opportunity.objects.filter(pk=records.opportunity.pk).exists()
        )
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert set(connection.introspection.table_names()) == tables and not MigrationExecutor(
        connection
    ).migration_plan(targets)
    test_five_named_restrict_references_include_lifecycle_revision()
    test_indexes_preserve_null_channel_uniqueness_and_dispatch_predicates()
