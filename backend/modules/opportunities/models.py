"""T18–T22: oportunidades, financiación declarada y contactos públicos propios."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Lower, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class TimestampedRecord(models.Model):
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


class OpportunityRecord(TimestampedRecord):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )

    class Meta:
        abstract = True


class Opportunity(OpportunityRecord):
    class Lifecycle(models.TextChoices):
        DRAFT = "draft", "Borrador técnico"
        ACTIVE = "active", "Activa"
        CLOSED = "closed", "Cerrada"
        EXPIRED = "expired", "Vencida"

    class Visibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        HIDDEN = "hidden", "Oculta"
        REMOVED = "removed", "Retirada"

    owner_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="owned_opportunities",
        null=True,
        blank=True,
        db_index=False,
    )
    owner_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.RESTRICT,
        related_name="owned_opportunities",
        null=True,
        blank=True,
        db_index=False,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="authored_opportunities",
        db_index=False,
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    area = models.CharField(max_length=150)
    responsible_label = models.CharField(max_length=200)
    lifecycle = models.CharField(
        max_length=16, choices=Lifecycle.choices, default=Lifecycle.DRAFT, db_default="draft"
    )
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.VISIBLE, db_default="visible"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    row_version = models.IntegerField(default=1, db_default=1)
    validity_revision = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = "opportunities_opportunity"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(owner_account__isnull=True, owner_organization__isnull=False)
                | models.Q(owner_account__isnull=False, owner_organization__isnull=True),
                name="ck_t18_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("title")), models.Value(0)), name="ck_t18_02"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("description")), models.Value(0)),
                name="ck_t18_03",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("area")), models.Value(0)), name="ck_t18_04"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("responsible_label")), models.Value(0)),
                name="ck_t18_05",
            ),
            models.CheckConstraint(
                condition=models.Q(lifecycle__in=["draft", "active", "closed", "expired"]),
                name="ck_t18_06",
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=["visible", "hidden", "removed"]),
                name="ck_t18_07",
            ),
            models.CheckConstraint(condition=models.Q(row_version__gt=0), name="ck_t18_08"),
            models.CheckConstraint(condition=models.Q(validity_revision__gte=0), name="ck_t18_09"),
            models.CheckConstraint(
                condition=models.Q(lifecycle="draft")
                | models.Q(
                    published_at__isnull=False, expires_at__isnull=False, validity_revision__gt=0
                ),
                name="ck_t18_10",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__isnull=True)
                | models.Q(published_at__isnull=True)
                | models.Q(expires_at__gt=models.F("published_at")),
                name="ck_t18_11",
            ),
        ]
        indexes = [
            models.Index(
                fields=["expires_at"], condition=models.Q(lifecycle="active"), name="ix_t18_01"
            ),
            models.Index(fields=["-published_at", "id"], name="ix_t18_02"),
            models.Index(Lower("area"), name="ix_t18_03"),
            models.Index(fields=["owner_account"], name="ix_t18_04"),
            models.Index(fields=["owner_organization"], name="ix_t18_05"),
            models.Index(fields=["author"], name="ix_t18_06"),
        ]


class LifecycleEvent(models.Model):
    """T19: historial; la transición válida y su actualización conjunta son del caso."""

    class Kind(models.TextChoices):
        PUBLISH = "publish", "Publicar"
        CLOSE = "close", "Cerrar"
        EXTEND = "extend", "Extender"
        EXPIRE = "expire", "Vencer"
        REACTIVATE = "reactivate", "Reactivar"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.RESTRICT, related_name="lifecycle_events", db_index=False
    )
    validity_revision = models.IntegerField()
    event_kind = models.CharField(max_length=16, choices=Kind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="opportunity_lifecycle_events",
        null=True,
        blank=True,
        db_index=False,
    )
    from_state = models.CharField(max_length=16, choices=Opportunity.Lifecycle.choices)
    to_state = models.CharField(
        max_length=16,
        choices=[
            (value, label) for value, label in Opportunity.Lifecycle.choices if value != "draft"
        ],
    )
    previous_expires_at = models.DateTimeField(null=True, blank=True)
    new_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = "opportunities_lifecycle_event"
        constraints = [
            models.UniqueConstraint(
                fields=["opportunity", "validity_revision"], name="uq_t19_key01"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    event_kind__in=["publish", "close", "extend", "expire", "reactivate"]
                ),
                name="ck_t19_01",
            ),
            models.CheckConstraint(
                condition=models.Q(from_state__in=["draft", "active", "closed", "expired"]),
                name="ck_t19_02",
            ),
            models.CheckConstraint(
                condition=models.Q(to_state__in=["active", "closed", "expired"]), name="ck_t19_03"
            ),
            models.CheckConstraint(condition=models.Q(validity_revision__gt=0), name="ck_t19_04"),
            models.CheckConstraint(
                condition=models.Q(event_kind="expire", actor__isnull=True)
                | (~models.Q(event_kind="expire") & models.Q(actor__isnull=False)),
                name="ck_t19_05",
            ),
        ]
        indexes = [models.Index(fields=["actor"], name="ix_t19_01")]

    def __str__(self):
        return str(self.pk)


class Need(OpportunityRecord):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.RESTRICT, related_name="needs", db_index=False
    )
    description = models.TextField()
    discipline = models.ForeignKey(
        "academics.Discipline",
        on_delete=models.RESTRICT,
        related_name="opportunity_needs",
        null=True,
        blank=True,
        db_index=False,
    )
    sort_order = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = "opportunities_need"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("description")), models.Value(0)),
                name="ck_t20_01",
            ),
            models.CheckConstraint(condition=models.Q(sort_order__gte=0), name="ck_t20_02"),
        ]
        indexes = [
            models.Index(fields=["opportunity"], name="ix_t20_01"),
            models.Index(fields=["discipline"], name="ix_t20_02"),
        ]


class Funding(TimestampedRecord):
    """T21: la fila identifica financiación declarada; no registra cobros ni pagos."""

    class Coverage(models.TextChoices):
        PROJECT = "project", "Proyecto"
        COLLABORATION = "collaboration", "Colaboración"

    class PaymentKind(models.TextChoices):
        ONE_OFF = "one_off", "Único"
        MONTHLY = "monthly", "Mensual"
        OTHER = "other", "Otra modalidad"

    opportunity = models.OneToOneField(
        Opportunity,
        primary_key=True,
        on_delete=models.RESTRICT,
        related_name="funding",
        db_index=False,
    )
    estimated_amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency_code = models.CharField(max_length=3)
    coverage = models.CharField(max_length=16, choices=Coverage.choices)
    payment_kind = models.CharField(max_length=16, choices=PaymentKind.choices)
    payment_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "opportunities_funding"
        constraints = [
            models.CheckConstraint(condition=models.Q(estimated_amount__gte=0), name="ck_t21_01"),
            models.CheckConstraint(
                condition=models.Q(currency_code__regex=r"^[A-Z]{3}$"), name="ck_t21_02"
            ),
            models.CheckConstraint(
                condition=~models.Q(payment_kind="other")
                | (
                    models.Q(payment_detail__isnull=False)
                    & GreaterThan(Length(Trim("payment_detail")), models.Value(0))
                ),
                name="ck_t21_03",
            ),
            models.CheckConstraint(
                condition=models.Q(coverage__in=["project", "collaboration"]), name="ck_t21_04"
            ),
            models.CheckConstraint(
                condition=models.Q(payment_kind__in=["one_off", "monthly", "other"]),
                name="ck_t21_05",
            ),
        ]


class OpportunityContact(OpportunityRecord):
    """T22: valor destinado a publicación, sin FK a contactos privados de M02."""

    class Kind(models.TextChoices):
        EMAIL = "email", "Correo"
        PHONE = "phone", "Teléfono"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"

    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.RESTRICT, related_name="public_contacts", db_index=False
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    value = models.CharField(max_length=320)
    label = models.CharField(max_length=80, null=True, blank=True)
    sort_order = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = "opportunities_contact"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["email", "phone", "whatsapp", "telegram"]),
                name="ck_t22_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("value")), models.Value(0)), name="ck_t22_02"
            ),
            models.CheckConstraint(condition=models.Q(sort_order__gte=0), name="ck_t22_03"),
            models.UniqueConstraint(fields=["opportunity", "kind", "value"], name="uq_t22_01"),
        ]
