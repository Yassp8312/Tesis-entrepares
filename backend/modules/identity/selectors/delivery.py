"""M01: destino y metadatos actuales para preparación interna de correo."""

from django.db import connection

from modules.identity.contracts.delivery import ChallengeDeliveryState
from modules.identity.models import EmailChallenge


def get_challenge_owner(*, challenge_id):
    return (
        EmailChallenge.objects.filter(pk=challenge_id).values_list("account_id", flat=True).first()
    )


def lock_delivery_challenge(*, challenge_id, account_id) -> ChallengeDeliveryState | None:
    if not connection.in_atomic_block:
        raise RuntimeError("El origen de correo requiere una transacción explícita.")
    row = (
        EmailChallenge.objects.filter(pk=challenge_id, account_id=account_id)
        .select_for_update()
        .values_list(
            "id",
            "account_id",
            "purpose",
            "key_version",
            "expires_at",
            "consumed_at",
            "invalidated_at",
            "email_snapshot",
        )
        .first()
    )
    return ChallengeDeliveryState(*row) if row else None
