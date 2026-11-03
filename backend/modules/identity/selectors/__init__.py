"""Lecturas propietarias de M01; el consumidor aplica su autorización y proyección."""

from uuid import UUID

from modules.identity.contracts import AccountState
from modules.identity.models import Account


def get_account_state(*, account_id: UUID) -> AccountState | None:
    """Lee únicamente la identidad y habilitación técnica actuales de la cuenta."""
    row = Account.objects.filter(pk=account_id).values_list("id", "is_active").first()
    if row is None:
        return None
    return AccountState(account_id=row[0], is_active=row[1])
