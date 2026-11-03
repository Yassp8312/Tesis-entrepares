import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import authenticate, get_user
from django.contrib.auth import login as django_login
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory
from django.utils import timezone

from modules.identity.models import Account

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
PASSWORD = "Muestra#72-Ciencia#Mar"


@pytest.fixture(scope="module")
def encoded_password():
    return make_password(PASSWORD)


def test_real_schema_matches_t01_and_does_not_create_default_user():
    assert connection.vendor == "postgresql"
    assert 170000 <= connection.pg_version < 180000
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        columns = connection.introspection.get_table_description(cursor, "identity_account")
        constraints = connection.introspection.get_constraints(cursor, "identity_account")
    assert "identity_account" in tables and "auth_user" not in tables
    assert "identity_account_groups" in tables and "identity_account_user_permissions" in tables
    assert {column.name for column in columns} == {
        "id",
        "email",
        "password",
        "is_active",
        "is_staff",
        "is_superuser",
        "last_login",
        "date_joined",
        "updated_at",
    }
    assert constraints["uq_t01_01"]["unique"]
    assert constraints["ck_t01_01"]["check"] and constraints["ck_t01_02"]["check"]


def test_account_persists_with_hash_and_case_insensitive_lookup():
    account = Account.objects.create_user("  Estudiante@Example.ORG  ", PASSWORD)
    account.refresh_from_db()
    assert isinstance(account.pk, uuid.UUID)
    assert account.email == "Estudiante@Example.ORG"
    assert account.password != PASSWORD and account.check_password(PASSWORD)
    assert Account.objects.get_by_natural_key("ESTUDIANTE@example.org").pk == account.pk
    assert timezone.is_aware(account.date_joined) and timezone.is_aware(account.updated_at)


def test_unique_index_rejects_case_variant_and_rolls_back():
    Account.objects.create_user("estudiante@example.org", PASSWORD)
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            Account.objects.create_user("ESTUDIANTE@EXAMPLE.ORG", PASSWORD)
    assert error.value.__cause__.diag.constraint_name == "uq_t01_01"
    assert Account.objects.count() == 1


@pytest.mark.parametrize(
    "email,password,constraint",
    [
        ("", None, "ck_t01_01"),
        ("   ", None, "ck_t01_01"),
        ("estudiante@example.org", "", "ck_t01_02"),
        ("estudiante@example.org", "   ", "ck_t01_02"),
    ],
)
def test_checks_are_enforced_by_postgresql(email, password, constraint, encoded_password):
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO identity_account (email,password) VALUES (%s,%s)",
                [email, encoded_password if password is None else password],
            )
    assert error.value.__cause__.diag.constraint_name == constraint
    assert Account.objects.count() == 0


def test_database_defaults_work_without_orm(encoded_password):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO identity_account (email,password) VALUES (%s,%s) "
            "RETURNING id,is_active,is_staff,is_superuser,date_joined,updated_at",
            ["directo@example.org", encoded_password],
        )
        identifier, active, staff, superuser, joined, updated = cursor.fetchone()
    assert isinstance(identifier, uuid.UUID)
    assert active and not staff and not superuser
    assert timezone.is_aware(joined) and joined == updated


def test_partial_save_updates_timestamp_in_database():
    account = Account.objects.create_user("estudiante@example.org", PASSWORD)
    old = timezone.now() - timedelta(minutes=1)
    Account.objects.filter(pk=account.pk).update(updated_at=old)
    account.last_login = timezone.now()
    account.save(update_fields=["last_login"])
    account.refresh_from_db()
    assert account.updated_at > old


def test_authentication_reads_real_account_and_respects_technical_disable():
    account = Account.objects.create_user("Estudiante@example.org", PASSWORD)
    assert authenticate(email=" ESTUDIANTE@EXAMPLE.ORG ", password=PASSWORD).pk == account.pk
    assert authenticate(email=account.email, password="incorrecta") is None
    account.is_active = False
    account.save(update_fields=["is_active"])
    assert authenticate(email=account.email, password=PASSWORD) is None


def test_server_session_restores_uuid_account():
    account = Account.objects.create_user("sesion@example.org", PASSWORD)
    request = RequestFactory().get("/")
    request.session = SessionStore()
    django_login(request, account, backend="config.authentication.EmailBackend")
    request.session.save()
    recovered = RequestFactory().get("/")
    recovered.session = SessionStore(session_key=request.session.session_key)
    assert get_user(recovered).pk == account.pk


def test_database_roles_keep_development_and_tests_separate():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        )
        assert cursor.fetchone() == (False, True, False, False, False)
        cursor.execute("SELECT rolcreatedb FROM pg_roles WHERE rolname='entrepares_dev'")
        assert cursor.fetchone() == (False,)
        cursor.execute(
            "SELECT has_database_privilege(current_user,'entrepares_development','CONNECT'), "
            "has_database_privilege('entrepares_dev',current_database(),'CONNECT')"
        )
        assert cursor.fetchone() == (False, False)
