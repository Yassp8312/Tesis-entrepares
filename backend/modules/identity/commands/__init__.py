"""Escrituras propietarias de M01; application coordina el registro completo."""

from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection

from core.clock import as_utc
from core.correlation import OperationContext
from modules.identity.contracts import (
    CONFIRMATION_EXAMPLE_KEY_VERSION,
    AccountState,
    ConfirmationConflict,
    ConfirmationState,
)
from modules.identity.models import Account, EmailChallenge
from modules.identity.selectors import lock_account_states, lock_confirmation


def create_account(*, email: str, password: str) -> AccountState:
    """Persiste solo T01, sin sesión, perfil, verificación, auditoría ni envío externo.

    El caso de aplicación debe coordinar los demás propietarios y su transacción.
    La creación ordinaria no acepta banderas de privilegio ni contraseña inutilizable.
    """
    if not isinstance(password, str):
        raise ValidationError("La creación ordinaria requiere una contraseña.")
    account = Account.objects.create_user(email=email, password=password)
    return AccountState(account_id=account.pk, is_active=account.is_active)


def create_confirmation_example(
    *, account_id: UUID, expires_at: datetime, operation: OperationContext
) -> ConfirmationState:
    """Solo T02; no firma, consume, verifica, autentica o envía una comprobación real."""
    expires_at = as_utc(expires_at)
    if not isinstance(operation, OperationContext):
        raise TypeError("La comprobación requiere contexto de operación.")
    if not connection.in_atomic_block:
        raise RuntimeError("La comprobación requiere la transacción del coordinador.")
    accounts = lock_account_states(account_ids=(account_id,))
    if not accounts or not accounts[0].is_active:
        raise ConfirmationConflict("La cuenta no admite la operación de muestra.")
    now = operation.now()
    if expires_at <= now:
        raise ConfirmationConflict("La vigencia debe terminar después del instante actual.")
    challenge = EmailChallenge.objects.create(
        account_id=account_id,
        purpose=EmailChallenge.Purpose.EMAIL_CONFIRMATION,
        email_snapshot=accounts[0].email,
        key_version=CONFIRMATION_EXAMPLE_KEY_VERSION,
        created_at=now,
        expires_at=expires_at,
    )
    return ConfirmationState(
        challenge.pk, account_id, challenge.purpose, expires_at, None, None, challenge.key_version
    )


def invalidate_confirmation_example(
    *, account_id: UUID, challenge_id: UUID, operation: OperationContext
) -> ConfirmationState:
    """Revalida T02 bajo bloqueo; conserva sus metadatos e historial."""
    if not isinstance(operation, OperationContext):
        raise TypeError("La comprobación requiere contexto de operación.")
    # Mismo orden que el coordinador: ancla de cuenta antes de comprobación.
    accounts = lock_account_states(account_ids=(account_id,))
    state = lock_confirmation(account_id=account_id, challenge_id=challenge_id)
    now = operation.now()
    if (
        not accounts
        or not accounts[0].is_active
        or state is None
        or state.purpose != EmailChallenge.Purpose.EMAIL_CONFIRMATION
        or state.key_version != CONFIRMATION_EXAMPLE_KEY_VERSION
        or state.consumed_at is not None
        or state.invalidated_at is not None
        or state.expires_at <= now
    ):
        raise ConfirmationConflict("La comprobación ya no admite la transición de muestra.")
    EmailChallenge.objects.filter(pk=challenge_id, account_id=account_id).update(invalidated_at=now)
    return ConfirmationState(
        challenge_id, account_id, state.purpose, state.expires_at, None, now, state.key_version
    )
