"""Escrituras propietarias de M01; application coordina el registro completo."""

from django.core.exceptions import ValidationError

from modules.identity.contracts import AccountState
from modules.identity.models import Account


def create_account(*, email: str, password: str) -> AccountState:
    """Persiste solo T01, sin sesión, perfil, verificación, auditoría ni envío externo.

    El caso de aplicación debe coordinar los demás propietarios y su transacción.
    La creación ordinaria no acepta banderas de privilegio ni contraseña inutilizable.
    """
    if not isinstance(password, str):
        raise ValidationError("La creación ordinaria requiere una contraseña.")
    account = Account.objects.create_user(email=email, password=password)
    return AccountState(account_id=account.pk, is_active=account.is_active)
