"""T34–T36: intención persistente e historial; los envíos se coordinan después del commit."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import Exact, GreaterThan
from django.utils import timezone


class PersistentRecord(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    updated_at = models.DateTimeField(auto_now=True, db_default=TransactionNow())

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)


class Notice(PersistentRecord):
    """La FK SQL referencia (opportunity_id, validity_revision) del evento de vigencia."""

    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.RESTRICT,
        related_name="scheduled_notices",
        db_constraint=False,
        db_index=False,
    )
    validity_revision = models.IntegerField()
    kind = models.CharField(max_length=32, default="expiry_reminder", db_default="expiry_reminder")
    scheduled_for = models.DateTimeField()
    channel = models.CharField(max_length=32, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notice"
        constraints = [
            models.CheckConstraint(condition=models.Q(kind="expiry_reminder"), name="ck_t34_01"),
            models.CheckConstraint(condition=models.Q(validity_revision__gt=0), name="ck_t34_02"),
            models.UniqueConstraint(
                fields=["opportunity", "validity_revision", "kind", "channel"],
                nulls_distinct=False,
                name="uq_t34_01",
            ),
        ]
        indexes = [
            models.Index(
                fields=["scheduled_for"],
                condition=models.Q(cancelled_at__isnull=True),
                name="ix_t34_02",
            )
        ]


class OutboxMessage(PersistentRecord):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "En proceso"
        SENT = "sent", "Aceptado por el canal"
        FAILED = "failed", "Fallido"
        CANCELLED = "cancelled", "Cancelado"

    notice = models.ForeignKey(
        Notice,
        on_delete=models.RESTRICT,
        related_name="outbox_messages",
        null=True,
        blank=True,
        db_index=False,
    )
    challenge = models.ForeignKey(
        "identity.EmailChallenge",
        on_delete=models.RESTRICT,
        related_name="outbox_messages",
        null=True,
        blank=True,
        db_index=False,
    )
    recipient_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="outbox_messages",
        null=True,
        blank=True,
        db_index=False,
    )
    channel = models.CharField(max_length=32)
    destination = models.TextField()
    template_key = models.CharField(max_length=80)
    payload = models.JSONField(default=dict, db_default={})
    idempotency_key = models.CharField(max_length=160)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_default="pending"
    )
    available_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    lease_until = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_outbox"
        constraints = [
            models.UniqueConstraint(fields=["idempotency_key"], name="uq_t35_key01"),
            models.CheckConstraint(
                condition=models.Q(notice__isnull=True, challenge__isnull=False)
                | models.Q(notice__isnull=False, challenge__isnull=True),
                name="ck_t35_01",
            ),
            models.CheckConstraint(
                condition=Exact(
                    models.Func(
                        models.F("payload"),
                        function="jsonb_typeof",
                        output_field=models.CharField(),
                    ),
                    models.Value("object"),
                ),
                name="ck_t35_02",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="processing") | models.Q(lease_until__isnull=False),
                name="ck_t35_03",
            ),
            models.CheckConstraint(
                condition=models.Q(status="sent", sent_at__isnull=False)
                | (~models.Q(status="sent") & models.Q(sent_at__isnull=True)),
                name="ck_t35_04",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["pending", "processing", "sent", "failed", "cancelled"]
                ),
                name="ck_t35_05",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("channel")), models.Value(0)), name="ck_t35_06"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("destination")), models.Value(0)),
                name="ck_t35_07",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("template_key")), models.Value(0)),
                name="ck_t35_08",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("idempotency_key")), models.Value(0)),
                name="ck_t35_09",
            ),
        ]
        indexes = [
            models.Index(
                fields=["available_at"],
                condition=models.Q(status__in=["pending", "failed"]),
                name="ix_t35_01",
            ),
            models.Index(
                fields=["lease_until"], condition=models.Q(status="processing"), name="ix_t35_02"
            ),
            models.Index(fields=["notice"], name="ix_t35_03"),
            models.Index(fields=["challenge"], name="ix_t35_04"),
            models.Index(fields=["recipient_account"], name="ix_t35_05"),
        ]


class DeliveryAttempt(models.Model):
    class Result(models.TextChoices):
        RUNNING = "running", "En curso"
        ACCEPTED = "accepted", "Aceptado"
        FAILED = "failed", "Fallido"
        UNKNOWN = "unknown", "Desconocido"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    outbox = models.ForeignKey(
        OutboxMessage, on_delete=models.RESTRICT, related_name="delivery_attempts", db_index=False
    )
    attempt_no = models.IntegerField()
    started_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(
        max_length=16, choices=Result.choices, default=Result.RUNNING, db_default="running"
    )
    provider_reference = models.TextField(null=True, blank=True)
    error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        db_table = "notifications_delivery_attempt"
        constraints = [
            models.UniqueConstraint(fields=["outbox", "attempt_no"], name="uq_t36_key01"),
            models.CheckConstraint(
                condition=models.Q(result__in=["running", "accepted", "failed", "unknown"]),
                name="ck_t36_01",
            ),
            models.CheckConstraint(condition=models.Q(attempt_no__gt=0), name="ck_t36_02"),
            models.CheckConstraint(
                condition=models.Q(finished_at__isnull=True)
                | models.Q(finished_at__gte=models.F("started_at")),
                name="ck_t36_03",
            ),
            models.CheckConstraint(
                condition=models.Q(result="running", finished_at__isnull=True)
                | (~models.Q(result="running") & models.Q(finished_at__isnull=False)),
                name="ck_t36_04",
            ),
        ]

    def __str__(self):
        return str(self.pk)
