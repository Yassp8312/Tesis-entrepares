"""T08–T11: catálogos y ámbitos; declarar una entrada no concede respaldo ni acceso."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Lower, Trim
from django.db.models.lookups import Exact, GreaterThan
from django.utils import timezone


class CatalogOrigin(models.TextChoices):
    CURATED = "curated", "Curada"
    DECLARED = "declared", "Declarada"


class AcademicRecord(models.Model):
    """Campos compartidos de M03; modelo abstracto sin tabla adicional."""

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


class Institution(AcademicRecord):
    """T08: homónimos admitidos, sin equivalencia automática con una organización."""

    class Kind(models.TextChoices):
        UNIVERSITY = "university", "Universidad"
        RESEARCH_CENTER = "research_center", "Centro de investigación"
        PRODUCTIVE = "productive", "Sector productivo"
        OTHER = "other", "Otra"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    origin = models.CharField(max_length=16, choices=CatalogOrigin.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="created_by",
        on_delete=models.RESTRICT,
        related_name="proposed_institutions",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "academics_institution"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("name")), models.Value(0)), name="ck_t08_01"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=["university", "research_center", "productive", "other"]
                ),
                name="ck_t08_02",
            ),
            models.CheckConstraint(
                condition=models.Q(origin__in=["curated", "declared"]), name="ck_t08_03"
            ),
        ]
        indexes = [
            models.Index(Lower("name"), name="ix_t08_01"),
            models.Index(fields=["created_by"], name="ix_t08_02"),
        ]


class AcademicScope(AcademicRecord):
    """T09: la migración protege (parent_id, institution_id) mediante una FK compuesta."""

    class Kind(models.TextChoices):
        INSTITUTION = "institution", "Institución"
        FACULTY = "faculty", "Facultad"
        CAREER = "career", "Carrera"
        OTHER = "other", "Otro"

    institution = models.ForeignKey(
        Institution, on_delete=models.RESTRICT, related_name="academic_scopes", db_index=False
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        related_name="children",
        null=True,
        blank=True,
        db_index=False,
        db_constraint=False,
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=Kind.choices)

    class Meta:
        db_table = "academics_scope"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("name")), models.Value(0)), name="ck_t09_01"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["institution", "faculty", "career", "other"]),
                name="ck_t09_02",
            ),
            models.CheckConstraint(
                condition=models.Q(parent__isnull=True) | ~models.Q(parent=models.F("id")),
                name="ck_t09_03",
            ),
            models.UniqueConstraint(fields=["id", "institution"], name="uq_t09_key01"),
        ]
        indexes = [
            models.Index(fields=["institution"], name="ix_t09_01"),
            models.Index(fields=["parent", "institution"], name="ix_t09_02"),
        ]


class Discipline(AcademicRecord):
    """T10: disciplina declarable; los nombres repetidos no se fusionan por texto."""

    name = models.CharField(max_length=200)
    origin = models.CharField(max_length=16, choices=CatalogOrigin.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="created_by",
        on_delete=models.RESTRICT,
        related_name="proposed_disciplines",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "academics_discipline"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("name")), models.Value(0)), name="ck_t10_01"
            ),
            models.CheckConstraint(
                condition=models.Q(origin__in=["curated", "declared"]), name="ck_t10_02"
            ),
        ]
        indexes = [
            models.Index(Lower("name"), name="ix_t10_01"),
            models.Index(fields=["created_by"], name="ix_t10_02"),
        ]


class InstitutionalDomain(AcademicRecord):
    """T11: dominio exacto y respaldo privado; PB03 delimita su administración."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RECOGNIZED = "recognized", "Reconocido"
        WITHDRAWN = "withdrawn", "Retirado"

    domain_ascii = models.CharField(max_length=253)
    institution = models.ForeignKey(
        Institution, on_delete=models.RESTRICT, related_name="institutional_domains", db_index=False
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_default="pending"
    )
    evidence_reference = models.TextField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="institutional_domain_decisions",
        null=True,
        blank=True,
        db_index=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "academics_domain"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("domain_ascii")), models.Value(0)),
                name="ck_t11_01",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "recognized", "withdrawn"]),
                name="ck_t11_02",
            ),
            models.CheckConstraint(
                condition=Exact(models.F("domain_ascii"), Lower(Trim("domain_ascii"))),
                name="ck_t11_03",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending")
                    | (
                        models.Q(
                            decided_by__isnull=False,
                            decided_at__isnull=False,
                            evidence_reference__isnull=False,
                        )
                        & GreaterThan(Length(Trim("evidence_reference")), models.Value(0))
                    )
                ),
                name="ck_t11_04",
            ),
            models.UniqueConstraint(fields=["domain_ascii"], name="uq_t11_key01"),
        ]
        indexes = [
            models.Index(fields=["institution"], name="ix_t11_01"),
            models.Index(fields=["decided_by"], name="ix_t11_02"),
        ]
