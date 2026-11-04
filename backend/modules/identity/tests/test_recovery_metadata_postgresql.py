"""Integridad T02/T03 real; datos sintéticos y ninguna operación pública habilitada."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from psycopg import sql

from modules.identity.models import Account, EmailChallenge, RecoveryRequest

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
EXPIRES = CREATED + timedelta(hours=1)


@pytest.fixture
def accounts():
    # Sin contraseñas utilizables; no se ensaya autenticación en esta tarea.
    return (
        Account.objects.create_user("solicitante@example.org"),
        Account.objects.create_user("revisor@example.org"),
    )


def insert_row(table, values):
    """SQL directo: no depende de full_clean(), choices ni save() para rechazar filas."""
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


def challenge_values(account, **changes):
    return {
        "account_id": account.pk,
        "purpose": "email_confirmation",
        "email_snapshot": "Entrega@Example.org",
        "created_at": CREATED,
        "expires_at": EXPIRES,
        **changes,
    }


def recovery_values(**changes):
    return {"claimed_email": "alegado@example.org", "statement": "Alegación sintética", **changes}


def assert_rejected(table, values, constraint):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            insert_row(table, values)
    assert error.value.__cause__.diag.constraint_name == constraint


def test_schema_preserves_columns_types_nullability_constraints_and_indexes():
    expected = {
        "identity_email_challenge": {
            "id": ("uuid", False),
            "account_id": ("uuid", False),
            "purpose": ("character varying(24)", False),
            "email_snapshot": ("character varying(254)", False),
            "key_version": ("character varying(32)", False),
            "expires_at": ("timestamp with time zone", False),
            "consumed_at": ("timestamp with time zone", True),
            "invalidated_at": ("timestamp with time zone", True),
            "created_at": ("timestamp with time zone", False),
        },
        "identity_recovery_request": {
            "id": ("uuid", False),
            "claimed_email": ("character varying(254)", False),
            "account_id": ("uuid", True),
            "reply_contact": ("text", True),
            "statement": ("text", False),
            "status": ("character varying(24)", False),
            "decided_by": ("uuid", True),
            "decided_at": ("timestamp with time zone", True),
            "decision_reason": ("text", True),
            "created_at": ("timestamp with time zone", False),
            "updated_at": ("timestamp with time zone", False),
        },
    }
    with connection.cursor() as cursor:
        for table, columns in expected.items():
            cursor.execute(
                "SELECT attname,format_type(atttypid,atttypmod),NOT attnotnull "
                "FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",
                [table],
            )
            assert {name: (kind, nullable) for name, kind, nullable in cursor} == columns
            constraints = connection.introspection.get_constraints(cursor, table)
            prefix = "t02" if table.endswith("challenge") else "t03"
            assert {k for k, v in constraints.items() if v["check"]} == {
                f"ck_{prefix}_{n:02}" for n in range(1, 6)
            }
            indexes = {k: v["columns"] for k, v in constraints.items() if v["index"]}
            assert indexes == (
                {"ix_t02_01": ["account_id", "purpose", "expires_at"]}
                if prefix == "t02"
                else {"ix_t03_01": ["account_id"], "ix_t03_02": ["decided_by"]}
            )
            if prefix == "t02":
                assert constraints["uq_t02_key01"]["unique"]
                assert constraints["uq_t02_key01"]["columns"] == ["id", "account_id"]
        cursor.execute(
            "SELECT conname,confdeltype,condeferrable,convalidated,confrelid::regclass::text "
            "FROM pg_constraint WHERE conrelid IN "
            "('identity_email_challenge'::regclass,'identity_recovery_request'::regclass) "
            "AND contype='f' ORDER BY conname"
        )
        assert cursor.fetchall() == [
            (name, "r", False, True, "identity_account")
            for name in ("fk_t02_01", "fk_t03_01", "fk_t03_02")
        ]


@pytest.mark.parametrize("purpose", ["email_confirmation", "password_reset"])
def test_challenge_sql_defaults_and_delivery_snapshot(accounts, purpose):
    account, _ = accounts
    identifier = insert_row(
        "identity_email_challenge",
        {
            "account_id": account.pk,
            "purpose": purpose,
            "email_snapshot": "Entrega@Example.org",
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        },
    )
    challenge = EmailChallenge.objects.get(pk=identifier)
    account.email = "otro@example.org"
    account.save(update_fields=["email"])
    challenge.refresh_from_db()
    assert isinstance(identifier, UUID)
    assert challenge.key_version == "v1" and challenge.purpose == purpose
    assert challenge.email_snapshot == "Entrega@Example.org"
    assert challenge.consumed_at is None and challenge.invalidated_at is None
    assert challenge.created_at.utcoffset() == timedelta(0)
    assert challenge.created_at < challenge.expires_at
    assert str(challenge) == str(identifier)


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"purpose": "other"}, "ck_t02_01"),
        ({"email_snapshot": ""}, "ck_t02_02"),
        ({"email_snapshot": "   "}, "ck_t02_02"),
        ({"key_version": ""}, "ck_t02_03"),
        ({"key_version": "   "}, "ck_t02_03"),
        ({"expires_at": CREATED}, "ck_t02_04"),
        ({"expires_at": CREATED - timedelta(microseconds=1)}, "ck_t02_04"),
        ({"consumed_at": CREATED, "invalidated_at": CREATED}, "ck_t02_05"),
    ],
)
def test_challenge_checks_reject_direct_sql(accounts, changes, constraint):
    assert_rejected(
        "identity_email_challenge", challenge_values(accounts[0], **changes), constraint
    )
    assert EmailChallenge.objects.count() == 0


@pytest.mark.parametrize("terminal_field", ["consumed_at", "invalidated_at"])
def test_challenge_accepts_each_terminal_state_and_blocks_conflicting_update(
    accounts, terminal_field
):
    identifier = insert_row(
        "identity_email_challenge", challenge_values(accounts[0], **{terminal_field: CREATED})
    )
    other_field = "invalidated_at" if terminal_field == "consumed_at" else "consumed_at"
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            EmailChallenge.objects.filter(pk=identifier).update(**{other_field: CREATED})
    assert error.value.__cause__.diag.constraint_name == "ck_t02_05"
    assert getattr(EmailChallenge.objects.get(pk=identifier), other_field) is None


def test_pending_recovery_sql_defaults_do_not_resolve_alleged_identity(accounts):
    account, _ = accounts
    identifier = insert_row(
        "identity_recovery_request", recovery_values(claimed_email=account.email)
    )
    request = RecoveryRequest.objects.get(pk=identifier)
    assert isinstance(identifier, UUID) and request.status == "pending"
    assert request.account_id is None and request.decided_by_id is None
    assert request.reply_contact is None and request.decision_reason is None
    assert request.decided_at is None and request.created_at == request.updated_at
    assert request.created_at.utcoffset() == timedelta(0)
    assert str(request) == str(identifier)
    account.refresh_from_db()
    assert not account.has_usable_password() and not account.is_staff and not account.is_superuser


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"status": "other"}, "ck_t03_01"),
        ({"claimed_email": ""}, "ck_t03_02"),
        ({"claimed_email": "   "}, "ck_t03_02"),
        ({"statement": ""}, "ck_t03_03"),
        ({"statement": "   "}, "ck_t03_03"),
        ({"decided_at": CREATED}, "ck_t03_04"),
        ({"decided_by": "reviewer"}, "ck_t03_04"),
        ({"status": "rejected"}, "ck_t03_04"),
        ({"status": "rejected", "decided_at": CREATED}, "ck_t03_04"),
        ({"status": "rejected", "decided_by": "reviewer"}, "ck_t03_04"),
        (
            {"status": "rejected", "decided_at": CREATED, "decided_by": "reviewer"},
            "ck_t03_04",
        ),
        (
            {
                "status": "rejected",
                "decided_at": CREATED,
                "decided_by": "reviewer",
                "decision_reason": "   ",
            },
            "ck_t03_04",
        ),
        (
            {
                "status": "approved",
                "decided_at": CREATED,
                "decided_by": "reviewer",
                "decision_reason": "Motivo sintético",
            },
            "ck_t03_05",
        ),
    ],
)
def test_recovery_checks_reject_direct_sql(accounts, changes, constraint):
    if changes.get("decided_by") == "reviewer":
        changes = {**changes, "decided_by": accounts[1].pk}
    assert_rejected("identity_recovery_request", recovery_values(**changes), constraint)
    assert RecoveryRequest.objects.count() == 0


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_complete_decision_preserves_private_data_without_granting_access(accounts, status):
    account, reviewer = accounts
    identifier = insert_row(
        "identity_recovery_request",
        recovery_values(
            account_id=account.pk if status == "approved" else None,
            reply_contact="seguimiento@example.org",
            status=status,
            decided_by=reviewer.pk,
            decided_at=CREATED,
            decision_reason="Comprobación sintética, sin validez institucional",
        ),
    )
    request = RecoveryRequest.objects.get(pk=identifier)
    assert request.status == status and request.decided_by == reviewer
    assert request.reply_contact == "seguimiento@example.org"
    account.refresh_from_db()
    assert not account.has_usable_password() and not account.is_staff and not account.is_superuser


@pytest.mark.parametrize(
    "table,field,constraint",
    [
        ("identity_email_challenge", "account_id", "fk_t02_01"),
        ("identity_recovery_request", "account_id", "fk_t03_01"),
        ("identity_recovery_request", "decided_by", "fk_t03_02"),
    ],
)
def test_references_reject_nonexistent_accounts_immediately(accounts, table, field, constraint):
    values = challenge_values(accounts[0]) if table.endswith("challenge") else recovery_values()
    if field == "decided_by":
        values.update(status="rejected", decided_at=CREATED, decision_reason="Motivo sintético")
    values[field] = uuid4()
    assert_rejected(table, values, constraint)


@pytest.mark.parametrize("reference", ["challenge", "recovery_account", "recovery_reviewer"])
@pytest.mark.parametrize("via_orm", [False, True])
def test_referenced_account_cannot_be_deleted_or_cascaded(accounts, reference, via_orm):
    account, reviewer = accounts
    if reference == "challenge":
        insert_row("identity_email_challenge", challenge_values(account))
        target, constraint = account, "fk_t02_01"
    else:
        values = recovery_values(account_id=account.pk)
        target, constraint = account, "fk_t03_01"
        if reference == "recovery_reviewer":
            values.update(
                status="rejected",
                decided_by=reviewer.pk,
                decided_at=CREATED,
                decision_reason="Motivo sintético",
            )
            target, constraint = reviewer, "fk_t03_02"
        insert_row("identity_recovery_request", values)
    with pytest.raises(RestrictedError if via_orm else IntegrityError) as error:
        with transaction.atomic():
            if via_orm:
                target.delete()
            else:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM identity_account WHERE id=%s", [target.pk])
    if not via_orm:
        assert error.value.__cause__.diag.constraint_name == constraint
    assert Account.objects.count() == 2
    assert EmailChallenge.objects.count() + RecoveryRequest.objects.count() == 1


def test_unique_pair_supports_future_composite_foreign_key(accounts):
    # Sonda dentro de la transacción de prueba, retirada por su rollback; no es T12.
    assert connection.settings_dict["NAME"] == "test_entrepares"
    challenge = insert_row("identity_email_challenge", challenge_values(accounts[0]))
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE synthetic_challenge_reference (challenge_id uuid,account_id uuid,"
            "CONSTRAINT synthetic_fk FOREIGN KEY (challenge_id,account_id) "
            "REFERENCES identity_email_challenge(id,account_id))"
        )
        cursor.execute(
            "INSERT INTO synthetic_challenge_reference VALUES (%s,%s)",
            [challenge, accounts[0].pk],
        )
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO synthetic_challenge_reference VALUES (%s,%s)",
                [challenge, accounts[1].pk],
            )
    assert error.value.__cause__.diag.constraint_name == "synthetic_fk"


def test_transaction_rolls_back_both_metadata_tables(accounts):
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            insert_row("identity_email_challenge", challenge_values(accounts[0]))
            insert_row("identity_recovery_request", recovery_values(account_id=accounts[0].pk))
            raise RuntimeError("fallo sintético de coordinación")
    assert EmailChallenge.objects.count() == RecoveryRequest.objects.count() == 0
    assert Account.objects.count() == 2


def test_recovery_partial_save_updates_timestamp(accounts):
    identifier = insert_row(
        "identity_recovery_request", recovery_values(created_at=CREATED, updated_at=CREATED)
    )
    request = RecoveryRequest.objects.get(pk=identifier)
    request.reply_contact = "nuevo@example.org"
    request.save(update_fields=["reply_contact"])
    request.refresh_from_db()
    assert request.updated_at > CREATED and request.created_at == CREATED


@pytest.mark.django_db(transaction=True)
def test_migration_can_reverse_and_reapply_in_ephemeral_database():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    account = Account.objects.create_user("migracion@example.org")
    previous = [("identity", "0001_initial")]
    current = MigrationExecutor(connection).loader.graph.leaf_nodes()
    original_tables = set(connection.introspection.table_names())
    try:
        MigrationExecutor(connection).migrate(previous)
        tables = connection.introspection.table_names()
        assert "identity_email_challenge" not in tables
        assert "identity_recovery_request" not in tables
        assert Account.objects.filter(pk=account.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(current)
    test_schema_preserves_columns_types_nullability_constraints_and_indexes()
    assert set(connection.introspection.table_names()) == original_tables
    assert not MigrationExecutor(connection).migration_plan(current)
    assert Account.objects.filter(pk=account.pk).exists()
    assert EmailChallenge.objects.count() == RecoveryRequest.objects.count() == 0
