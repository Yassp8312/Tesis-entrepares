"""T08–T14: catálogos, ámbitos, respaldo personal y distinción de investigador."""

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


class PersonalVerification(AcademicRecord):
    """T12: expediente y respaldo; su creación no comprueba identidad o autoridad."""

    class Method(models.TextChoices):
        INSTITUTIONAL_EMAIL = "institutional_email", "Correo institucional"
        MANUAL = "manual", "Revisión manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        WITHDRAWN = "withdrawn", "Retirada"

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="personal_verifications",
        db_index=False,
    )
    method = models.CharField(max_length=24, choices=Method.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_default="pending"
    )
    challenge = models.ForeignKey(
        "identity.EmailChallenge",
        on_delete=models.RESTRICT,
        related_name="personal_verifications",
        null=True,
        blank=True,
        db_index=False,
        db_constraint=False,
    )
    domain = models.ForeignKey(
        InstitutionalDomain,
        on_delete=models.RESTRICT,
        related_name="personal_verifications",
        null=True,
        blank=True,
        db_index=False,
    )
    academic_scope = models.ForeignKey(
        AcademicScope,
        on_delete=models.RESTRICT,
        related_name="personal_verifications",
        null=True,
        blank=True,
        db_index=False,
    )
    evidence_reference = models.TextField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="personal_verification_decisions",
        null=True,
        blank=True,
        db_index=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "academics_personal_verification"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(method__in=["institutional_email", "manual"]), name="ck_t12_01"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "approved", "rejected", "withdrawn"]),
                name="ck_t12_02",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", decided_at__isnull=True, decided_by__isnull=True)
                    | (~models.Q(status="pending") & models.Q(decided_at__isnull=False))
                ),
                name="ck_t12_03",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        method="institutional_email",
                        challenge__isnull=False,
                        domain__isnull=False,
                        academic_scope__isnull=True,
                    )
                    | models.Q(
                        method="manual",
                        challenge__isnull=True,
                        domain__isnull=True,
                        academic_scope__isnull=False,
                    )
                ),
                name="ck_t12_04",
            ),
            models.CheckConstraint(
                condition=models.Q(status="pending")
                | (
                    models.Q(decision_reason__isnull=False)
                    & GreaterThan(Length(Trim("decision_reason")), models.Value(0))
                ),
                name="ck_t12_05",
            ),
            models.CheckConstraint(
                condition=~models.Q(method="manual")
                | models.Q(status="pending")
                | models.Q(decided_by__isnull=False),
                name="ck_t12_06",
            ),
            models.UniqueConstraint(
                fields=["challenge"], condition=models.Q(challenge__isnull=False), name="uq_t12_01"
            ),
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(method="manual", status="pending"),
                name="uq_t12_02",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "status"], name="ix_t12_03"),
            models.Index(fields=["challenge", "account"], name="ix_t12_04"),
            models.Index(fields=["domain"], name="ix_t12_05"),
            models.Index(fields=["academic_scope"], name="ix_t12_06"),
            models.Index(fields=["decided_by"], name="ix_t12_07"),
        ]


class ResearcherRequest(AcademicRecord):
    """T13: proponer o resolver una solicitud no crea por sí solo una concesión T14."""

    class Decision(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="researcher_requests",
        db_index=False,
    )
    academic_scope = models.ForeignKey(
        AcademicScope, on_delete=models.RESTRICT, related_name="researcher_requests", db_index=False
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="requested_by",
        on_delete=models.RESTRICT,
        related_name="proposed_researcher_requests",
        db_index=False,
    )
    justification = models.TextField()
    decision = models.CharField(
        max_length=16, choices=Decision.choices, default=Decision.PENDING, db_default="pending"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="researcher_request_decisions",
        null=True,
        blank=True,
        db_index=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "academics_researcher_request"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("justification")), models.Value(0)),
                name="ck_t13_01",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=["pending", "approved", "rejected"]),
                name="ck_t13_02",
            ),
            models.CheckConstraint(
                condition=models.Q(decision="pending")
                | (
                    models.Q(
                        decided_by__isnull=False,
                        decided_at__isnull=False,
                        decision_reason__isnull=False,
                    )
                    & GreaterThan(Length(Trim("decision_reason")), models.Value(0))
                ),
                name="ck_t13_03",
            ),
            models.UniqueConstraint(
                fields=["id", "account", "academic_scope"], name="uq_t13_key01"
            ),
        ]
        indexes = [
            models.Index(fields=["account"], name="ix_t13_01"),
            models.Index(fields=["requested_by"], name="ix_t13_02"),
            models.Index(fields=["decided_by"], name="ix_t13_03"),
            models.Index(fields=["academic_scope"], name="ix_t13_04"),
        ]


class ResearcherAward(AcademicRecord):
    """T14: concesión directa o procedente de una solicitud de la misma persona y ámbito."""

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="researcher_awards",
        db_index=False,
    )
    academic_scope = models.ForeignKey(
        AcademicScope, on_delete=models.RESTRICT, related_name="researcher_awards", db_index=False
    )
    source_request = models.ForeignKey(
        ResearcherRequest,
        on_delete=models.RESTRICT,
        related_name="awards",
        null=True,
        blank=True,
        db_index=False,
        db_constraint=False,
    )
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="awarded_by",
        on_delete=models.RESTRICT,
        related_name="granted_researcher_awards",
        db_index=False,
    )
    justification = models.TextField()
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="ended_by",
        on_delete=models.RESTRICT,
        related_name="ended_researcher_awards",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "academics_researcher_award"
        constraints = [
            models.UniqueConstraint(fields=["source_request"], name="uq_t14_key01"),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("justification")), models.Value(0)),
                name="ck_t14_01",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True, ended_by__isnull=True)
                | models.Q(ended_at__isnull=False, ended_by__isnull=False),
                name="ck_t14_02",
            ),
            models.UniqueConstraint(
                fields=["account", "academic_scope"],
                condition=models.Q(ended_at__isnull=True),
                name="uq_t14_01",
            ),
        ]
        indexes = [
            models.Index(fields=["account"], name="ix_t14_02"),
            models.Index(fields=["awarded_by"], name="ix_t14_03"),
            models.Index(fields=["ended_by"], name="ix_t14_04"),
            models.Index(fields=["academic_scope"], name="ix_t14_05"),
            models.Index(fields=["source_request", "account", "academic_scope"], name="ix_t14_06"),
        ]
