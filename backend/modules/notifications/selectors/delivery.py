"""Proyecciones propietarias de salida; no retornan modelos o payloads al cliente."""

import json

from django.db import connection

from modules.notifications.contracts.delivery import (
    NoticeDeliveryState,
    OutboxEnvelope,
    OutboxOrigin,
)
from modules.notifications.models import Notice, OutboxMessage


def get_outbox_origin(*, outbox_id) -> OutboxOrigin | None:
    row = (
        OutboxMessage.objects.filter(pk=outbox_id)
        .values_list("id", "recipient_account_id", "challenge_id", "notice_id")
        .first()
    )
    return OutboxOrigin(*row) if row else None


def get_outbox_envelope(*, outbox_id) -> OutboxEnvelope | None:
    row = (
        OutboxMessage.objects.filter(pk=outbox_id)
        .values_list(
            "id",
            "recipient_account_id",
            "challenge_id",
            "notice_id",
            "channel",
            "template_key",
            "idempotency_key",
            "destination",
            "payload",
        )
        .first()
    )
    return OutboxEnvelope(OutboxOrigin(*row[:4]), *row[4:8], json.dumps(row[8])) if row else None


def get_notice_opportunity(*, notice_id):
    return Notice.objects.filter(pk=notice_id).values_list("opportunity_id", flat=True).first()


def lock_notice(*, notice_id) -> NoticeDeliveryState | None:
    if not connection.in_atomic_block:
        raise RuntimeError("El aviso requiere la transacción del coordinador.")
    row = (
        Notice.objects.filter(pk=notice_id)
        .select_for_update()
        .values_list(
            "id", "opportunity_id", "validity_revision", "scheduled_for", "channel", "cancelled_at"
        )
        .first()
    )
    return NoticeDeliveryState(*row) if row else None
