import asyncio
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from config.authentication import EmailBackend
from modules.identity.checks import check_account_identity
from modules.identity.models import Account, AccountManager

PASSWORD = "Muestra#72-Ciencia#Mar"


@pytest.fixture
def unsaved_manager(monkeypatch):
    # La persistencia real y las restricciones se probarán sobre PostgreSQL en T04.
    monkeypatch.setattr(Account, "save", lambda self, **kwargs: None)
    return Account.objects


def test_custom_user_matches_t01_without_profile_or_verification_columns():
    assert get_user_model() is Account
    assert Account._meta.db_table == "identity_account"
    assert {f.column for f in Account._meta.local_fields} == {
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
    account = Account(email="Estudiante@Example.ORG")
    assert isinstance(account.pk, uuid.UUID)
    assert account.is_active and not account.is_staff and not account.is_superuser


def test_creation_hashes_password_and_preserves_delivery_address(unsaved_manager):
    account = unsaved_manager.create_user("  Estudiante@Example.ORG  ", PASSWORD)
    assert account.email == "Estudiante@Example.ORG"
    assert account.password != PASSWORD
    assert account.password.startswith("pbkdf2_sha256$")
    assert account.check_password(PASSWORD)
    assert not account.check_password("Contraseña-distinta")
    assert not account.is_staff and not account.is_superuser


@pytest.mark.parametrize("email", [None, "", "   ", "sin-arroba"])
def test_creation_rejects_invalid_addresses_without_persistence(unsaved_manager, email):
    with pytest.raises((ValueError, ValidationError)):
        unsaved_manager.create_user(email, PASSWORD)


@pytest.mark.parametrize("password", ["12345678", "        ", "a" * 129])
def test_creation_enforces_password_policy(unsaved_manager, password):
    with pytest.raises(ValidationError):
        unsaved_manager.create_user("estudiante@example.org", password)


@pytest.mark.parametrize("privilege", ["is_staff", "is_superuser"])
def test_ordinary_creation_rejects_technical_privileges(unsaved_manager, privilege):
    with pytest.raises(ValueError):
        unsaved_manager.create_user("estudiante@example.org", PASSWORD, **{privilege: True})


def test_internal_account_without_password_is_unusable(unsaved_manager):
    account = unsaved_manager.create_user("interno@example.org")
    assert not account.has_usable_password()


def test_superuser_requires_correct_flags_and_password(unsaved_manager):
    with pytest.raises(ValueError):
        unsaved_manager.create_superuser("tecnico@example.org", PASSWORD, is_staff=False)
    with pytest.raises(ValueError):
        unsaved_manager.create_superuser("tecnico@example.org")
    account = unsaved_manager.create_superuser("tecnico@example.org", PASSWORD)
    assert account.is_staff and account.is_superuser and account.check_password(PASSWORD)


def test_lookup_uses_same_lower_expression_as_uniqueness(monkeypatch):
    captured = {}

    def capture_get(queryset, **kwargs):
        captured["sql"], captured["params"] = queryset.filter(**kwargs).query.sql_with_params()
        return "cuenta-sintetica"

    monkeypatch.setattr(QuerySet, "get", capture_get)
    assert Account.objects.get_by_natural_key(" Estudiante@Example.ORG ") == "cuenta-sintetica"
    assert 'LOWER("identity_account"."email") = (LOWER(%s))' in captured["sql"]
    assert captured["params"] == ("Estudiante@Example.ORG",)


def test_system_guard_detects_missing_case_insensitive_uniqueness(monkeypatch):
    assert check_account_identity() == []
    monkeypatch.setattr(Account._meta, "constraints", [])
    assert [error.id for error in check_account_identity()] == ["identity.E001"]


@pytest.mark.parametrize("active", [True, False])
def test_authentication_keeps_django_password_and_active_checks(monkeypatch, active):
    account = Account(email="Estudiante@Example.ORG", is_active=active)
    account.set_password(PASSWORD)
    received = []

    def find_account(manager, email):
        received.append(email)
        return account

    monkeypatch.setattr(AccountManager, "get_by_natural_key", find_account)
    authenticated = EmailBackend().authenticate(
        None, email=" ESTUDIANTE@example.org ", password=PASSWORD
    )
    assert received == ["ESTUDIANTE@example.org"]
    assert authenticated is account if active else authenticated is None
    assert EmailBackend().authenticate(None, email=account.email, password="incorrecta") is None


def test_async_authentication_uses_custom_lookup(monkeypatch):
    account = Account(email="estudiante@example.org")
    account.set_password(PASSWORD)

    async def find_account(manager, email):
        assert email == "ESTUDIANTE@example.org"
        return account

    monkeypatch.setattr(AccountManager, "aget_by_natural_key", find_account)
    assert (
        asyncio.run(
            EmailBackend().aauthenticate(None, email=" ESTUDIANTE@example.org ", password=PASSWORD)
        )
        is account
    )


def test_partial_save_keeps_updated_at(monkeypatch):
    from django.contrib.auth.base_user import AbstractBaseUser

    saved = {}
    monkeypatch.setattr(AbstractBaseUser, "save", lambda self, **kwargs: saved.update(kwargs))
    Account(email="estudiante@example.org").save(update_fields=["last_login"])
    assert saved["update_fields"] == {"last_login", "updated_at"}
