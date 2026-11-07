"""T23–T25: divulgación, datos de eventos y selecciones de contenido destacado."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
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


class PublicationRecord(TimestampedRecord):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )

    class Meta:
        abstract = True


class Publication(PublicationRecord):
    class Kind(models.TextChoices):
        NEWS = "news", "Novedad"
        EVENT = "event", "Evento"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador técnico"
        PUBLISHED = "published", "Publicada"
        WITHDRAWN = "withdrawn", "Retirada por su titular"

    class Visibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        HIDDEN = "hidden", "Oculta"
        REMOVED = "removed", "Retirada por moderación"

    owner_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="owned_publications",
        null=True,
        blank=True,
        db_index=False,
    )
    owner_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.RESTRICT,
        related_name="owned_publications",
        null=True,
        blank=True,
        db_index=False,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="authored_publications",
        db_index=False,
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_default="draft"
    )
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.VISIBLE, db_default="visible"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    row_version = models.IntegerField(default=1, db_default=1)

    class Meta:
        db_table = "publications_publication"
        constraints = [
            models.UniqueConstraint(fields=["id", "kind"], name="uq_t23_key01"),
            models.CheckConstraint(
                condition=models.Q(owner_account__isnull=True, owner_organization__isnull=False)
                | models.Q(owner_account__isnull=False, owner_organization__isnull=True),
                name="ck_t23_01",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["news", "event"]), name="ck_t23_02"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["draft", "published", "withdrawn"]), name="ck_t23_03"
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=["visible", "hidden", "removed"]),
                name="ck_t23_04",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("title")), models.Value(0)), name="ck_t23_05"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("body")), models.Value(0)), name="ck_t23_06"
            ),
            models.CheckConstraint(
                condition=models.Q(status="draft") | models.Q(published_at__isnull=False),
                name="ck_t23_07",
            ),
            models.CheckConstraint(condition=models.Q(row_version__gt=0), name="ck_t23_08"),
        ]
        indexes = [
            models.Index(fields=["-published_at", "id"], name="ix_t23_01"),
            models.Index(fields=["owner_account"], name="ix_t23_02"),
            models.Index(fields=["owner_organization"], name="ix_t23_03"),
            models.Index(fields=["author"], name="ix_t23_04"),
        ]


class EventDetail(TimestampedRecord):
    """La migración exige (publication_id, publication_kind) → Publication(id, kind)."""

    class Mode(models.TextChoices):
        IN_PERSON = "in_person", "Presencial"
        ONLINE = "online", "En línea"
        HYBRID = "hybrid", "Híbrido"

    class ContactKind(models.TextChoices):
        EMAIL = "email", "Correo"
        PHONE = "phone", "Teléfono"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"

    publication = models.OneToOneField(
        Publication,
        primary_key=True,
        on_delete=models.RESTRICT,
        related_name="event_detail",
        db_index=False,
        db_constraint=False,
    )
    publication_kind = models.CharField(max_length=16, default="event", db_default="event")
    event_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    time_zone = models.CharField(
        max_length=64, default="America/Havana", db_default="America/Havana"
    )
    mode = models.CharField(max_length=16, choices=Mode.choices)
    venue = models.TextField(null=True, blank=True)
    participation_url = models.TextField(null=True, blank=True)
    contact_kind = models.CharField(
        max_length=16, choices=ContactKind.choices, null=True, blank=True
    )
    contact_value = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "publications_event_detail"
        constraints = [
            models.CheckConstraint(condition=models.Q(publication_kind="event"), name="ck_t24_01"),
            models.CheckConstraint(
                condition=models.Q(contact_kind__isnull=True, contact_value__isnull=True)
                | models.Q(contact_kind__isnull=False, contact_value__isnull=False),
                name="ck_t24_02",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(participation_url__isnull=False)
                    & GreaterThan(Length(Trim("participation_url")), models.Value(0))
                )
                | (
                    models.Q(contact_value__isnull=False)
                    & GreaterThan(Length(Trim("contact_value")), models.Value(0))
                ),
                name="ck_t24_03",
            ),
            models.CheckConstraint(
                condition=models.Q(mode__in=["in_person", "online", "hybrid"]), name="ck_t24_04"
            ),
            models.CheckConstraint(
                condition=models.Q(contact_kind__in=["email", "phone", "whatsapp", "telegram"]),
                name="ck_t24_05",
            ),
            models.CheckConstraint(
                condition=models.Q(venue__isnull=True)
                | GreaterThan(Length(Trim("venue")), models.Value(0)),
                name="ck_t24_06",
            ),
            models.CheckConstraint(
                condition=models.Q(participation_url__isnull=True)
                | GreaterThan(Length(Trim("participation_url")), models.Value(0)),
                name="ck_t24_07",
            ),
            models.CheckConstraint(
                condition=models.Q(contact_value__isnull=True)
                | GreaterThan(Length(Trim("contact_value")), models.Value(0)),
                name="ck_t24_08",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("time_zone")), models.Value(0)), name="ck_t24_09"
            ),
        ]
        indexes = [models.Index(fields=["publication", "publication_kind"], name="ix_t24_01")]


class Highlight(PublicationRecord):
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.RESTRICT,
        related_name="highlights",
        null=True,
        blank=True,
        db_index=False,
    )
    publication = models.ForeignKey(
        Publication,
        on_delete=models.RESTRICT,
        related_name="highlights",
        null=True,
        blank=True,
        db_index=False,
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="granted_by",
        on_delete=models.RESTRICT,
        related_name="granted_highlights",
        db_index=False,
    )
    source_grant = models.ForeignKey(
        "access.Grant",
        on_delete=models.RESTRICT,
        related_name="highlights",
        null=True,
        blank=True,
        db_index=False,
    )
    starts_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    ends_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="revoked_by",
        on_delete=models.RESTRICT,
        related_name="revoked_highlights",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "publications_highlight"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(opportunity__isnull=True, publication__isnull=False)
                | models.Q(opportunity__isnull=False, publication__isnull=True),
                name="ck_t25_01",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_t25_02",
            ),
            models.CheckConstraint(
                condition=models.Q(revoked_at__isnull=True, revoked_by__isnull=True)
                | models.Q(revoked_at__isnull=False, revoked_by__isnull=False),
                name="ck_t25_03",
            ),
            models.UniqueConstraint(
                fields=["opportunity"],
                condition=models.Q(revoked_at__isnull=True, opportunity__isnull=False),
                name="uq_t25_01",
            ),
            models.UniqueConstraint(
                fields=["publication"],
                condition=models.Q(revoked_at__isnull=True, publication__isnull=False),
                name="uq_t25_02",
            ),
        ]
        indexes = [
            models.Index(fields=["opportunity"], name="ix_t25_03"),
            models.Index(fields=["publication"], name="ix_t25_04"),
            models.Index(fields=["granted_by"], name="ix_t25_05"),
            models.Index(fields=["source_grant"], name="ix_t25_06"),
            models.Index(fields=["revoked_by"], name="ix_t25_07"),
        ]
