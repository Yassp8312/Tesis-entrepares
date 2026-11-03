from dataclasses import FrozenInstanceError, asdict
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from modules.identity.commands import create_account
from modules.identity.contracts import AccountState
from modules.identity.models import Account
from modules.identity.selectors import get_account_state

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]
PASSWORD = "Muestra#72-Ciencia#Mar"


def test_command_persists_ordinary_account_and_returns_minimum_state():
    result = create_account(email=" Estado@Example.org ", password=PASSWORD)
    account = Account.objects.get(pk=result.account_id)
    assert isinstance(result, AccountState) and result.is_active
    assert account.email == "Estado@Example.org" and account.check_password(PASSWORD)
    assert not account.is_staff and not account.is_superuser
    assert set(asdict(result)) == {"account_id", "is_active"}
    with pytest.raises(FrozenInstanceError):
        result.is_active = False


def test_selector_reads_current_state_without_exposing_credentials(django_assert_num_queries):
    result = create_account(email="estado@example.org", password=PASSWORD)
    with django_assert_num_queries(1):
        assert get_account_state(account_id=result.account_id) == result
    Account.objects.filter(pk=result.account_id).update(is_active=False)
    assert get_account_state(account_id=result.account_id).is_active is False
    assert get_account_state(account_id=uuid4()) is None
    assert Account.objects.count() == 1


@pytest.mark.parametrize("password", [None, "corta"])
def test_command_rejects_absent_or_weak_password_without_creating_row(password):
    with pytest.raises(ValidationError):
        create_account(email="estado@example.org", password=password)
    assert Account.objects.count() == 0


def test_owner_command_uses_database_uniqueness_and_outer_rollback():
    create_account(email="estado@example.org", password=PASSWORD)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            create_account(email="ESTADO@EXAMPLE.ORG", password=PASSWORD)
    assert Account.objects.count() == 1
    with pytest.raises(RuntimeError, match="fallo sintético"):
        with transaction.atomic():
            create_account(email="revertir@example.org", password=PASSWORD)
            raise RuntimeError("fallo sintético del coordinador")
    assert not Account.objects.filter(email="revertir@example.org").exists()
