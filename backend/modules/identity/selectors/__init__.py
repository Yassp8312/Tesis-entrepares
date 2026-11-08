"""Lecturas propietarias de M01; el consumidor aplica su autorización y proyección."""

from uuid import UUID

from django.db import connection

from modules.identity.contracts import AccountState, ConfirmationState, LockedAccountState
from modules.identity.models import Account, EmailChallenge


def get_account_state(*, account_id: UUID) -> AccountState | None:
    """Lee únicamente la identidad y habilitación técnica actuales de la cuenta."""
    row = Account.objects.filter(pk=account_id).values_list("id", "is_active").first()
    if row is None:
        return None
    return AccountState(account_id=row[0], is_active=row[1])


def lock_account_states(*, account_ids: tuple[UUID, ...]) -> tuple[LockedAccountState, ...]:
    """Anclas M01 en orden UUID ascendente; conservar bloqueos hasta terminar el caso."""
    if (
        type(account_ids) is not tuple
        or not account_ids
        or any(not isinstance(value, UUID) for value in account_ids)
    ):
        raise TypeError("Se requieren identificadores internos de cuenta.")
    if not connection.in_atomic_block:
        raise RuntimeError("El bloqueo de cuentas requiere la transacción del coordinador.")
    rows = (
        Account.objects.filter(pk__in=set(account_ids))
        .order_by("pk")
        .select_for_update(of=("self",))
        .values_list("id", "is_active", "email")
    )
    return tuple(LockedAccountState(*row) for row in rows)


def lock_confirmation(*, account_id: UUID, challenge_id: UUID) -> ConfirmationState | None:
    """Se llama después de bloquear la cuenta; no abre comprobaciones de otro titular."""
    if not isinstance(account_id, UUID) or not isinstance(challenge_id, UUID):
        raise TypeError("Se requieren referencias internas de la comprobación.")
    if not connection.in_atomic_block:
        raise RuntimeError("La comprobación requiere una transacción explícita.")
    row = (
        EmailChallenge.objects.filter(pk=challenge_id, account_id=account_id)
        .select_for_update(of=("self",))
        .values_list(
            "id",
            "account_id",
            "purpose",
            "expires_at",
            "consumed_at",
            "invalidated_at",
            "key_version",
        )
        .first()
    )
    return ConfirmationState(*row) if row else None
