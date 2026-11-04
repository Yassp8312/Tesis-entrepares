"""T04–T07: perfil y declaraciones; el respaldo personal pertenece a M03."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class ProfileRecord(models.Model):
    """Campos compartidos de M02; modelo abstracto sin tabla propia."""

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


class Profile(ProfileRecord):
    """T04: un perfil por cuenta; completitud y acceso se derivan al operar."""

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="personal_profiles",
        db_index=False,
    )
    full_name = models.CharField(max_length=200)
    bio = models.TextField(null=True, blank=True)
    experience_summary = models.TextField(null=True, blank=True)
    experience_years = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    interests = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "profiles_profile"
        constraints = [
            models.UniqueConstraint(fields=["account"], name="uq_t04_key01"),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("full_name")), models.Value(0)), name="ck_t04_01"
            ),
            models.CheckConstraint(
                condition=models.Q(experience_years__isnull=True)
                | models.Q(experience_years__gte=0),
                name="ck_t04_02",
            ),
        ]


class Education(ProfileRecord):
    """T05: formación declarada, con antecedentes conservados al finalizar su vigencia."""

    class Condition(models.TextChoices):
        STUDENT = "student", "Estudiante"
        GRADUATE = "graduate", "Graduado"

    profile = models.ForeignKey(
        Profile, on_delete=models.RESTRICT, related_name="education_records", db_index=False
    )
    discipline = models.ForeignKey(
        "academics.Discipline",
        on_delete=models.RESTRICT,
        related_name="declared_education_records",
        db_index=False,
    )
    institution = models.ForeignKey(
        "academics.Institution",
        on_delete=models.RESTRICT,
        related_name="declared_education_records",
        db_index=False,
    )
    condition = models.CharField(max_length=16, choices=Condition.choices)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "profiles_education"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(condition__in=["student", "graduate"]), name="ck_t05_01"
            ),
            models.UniqueConstraint(
                fields=["profile", "discipline", "institution", "condition"],
                condition=models.Q(ended_at__isnull=True),
                name="uq_t05_01",
            ),
        ]
        indexes = [
            models.Index(fields=["profile"], name="ix_t05_02"),
            models.Index(fields=["discipline"], name="ix_t05_03"),
            models.Index(fields=["institution"], name="ix_t05_04"),
        ]


class Contact(ProfileRecord):
    """T06: contacto del perfil; is_visible solo se aplica en la bolsa autorizada."""

    class Kind(models.TextChoices):
        EMAIL = "email", "Correo"
        PHONE = "phone", "Teléfono"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"

    profile = models.ForeignKey(
        Profile, on_delete=models.RESTRICT, related_name="contacts", db_index=False
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    value = models.CharField(max_length=320)
    label = models.CharField(max_length=80, null=True, blank=True)
    is_visible = models.BooleanField(default=True, db_default=True)
    sort_order = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = "profiles_contact"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["email", "phone", "whatsapp", "telegram"]),
                name="ck_t06_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("value")), models.Value(0)), name="ck_t06_02"
            ),
            models.CheckConstraint(condition=models.Q(sort_order__gte=0), name="ck_t06_03"),
            models.UniqueConstraint(fields=["profile", "kind", "value"], name="uq_t06_01"),
        ]


class Merit(ProfileRecord):
    """T07: mérito declarado sin estado de aval ni distinción de investigador."""

    profile = models.ForeignKey(
        Profile, on_delete=models.RESTRICT, related_name="declared_merits", db_index=False
    )
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    awarded_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "profiles_merit"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("title")), models.Value(0)), name="ck_t07_01"
            ),
        ]
        indexes = [models.Index(fields=["profile"], name="ix_t07_01")]
