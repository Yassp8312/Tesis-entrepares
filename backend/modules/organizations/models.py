"""T15–T17: entidad, expediente y representación; independientes del respaldo personal."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Lower, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class OrganizationRecord(models.Model):
    """Base abstracta de M04; no crea otra tabla ni concede facultades."""

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


class Organization(OrganizationRecord):
    """T15: el vínculo con una institución del catálogo no verifica a la entidad."""

    class Kind(models.TextChoices):
        UNIVERSITY = "university", "Universidad"
        PRIVATE = "private", "Privada"
        STATE_OTHER = "state_other", "Otra entidad estatal"
        OTHER = "other", "Otra"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    institution = models.ForeignKey(
        "academics.Institution",
        on_delete=models.RESTRICT,
        related_name="linked_organizations",
        null=True,
        blank=True,
        db_index=False,
    )
    description = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="created_by",
        on_delete=models.RESTRICT,
        related_name="proposed_organizations",
        db_index=False,
    )

    class Meta:
        db_table = "organizations_organization"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("name")), models.Value(0)), name="ck_t15_01"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["university", "private", "state_other", "other"]),
                name="ck_t15_02",
            ),
        ]
        indexes = [
            models.Index(Lower("name"), name="ix_t15_01"),
            models.Index(fields=["institution"], name="ix_t15_02"),
            models.Index(fields=["created_by"], name="ix_t15_03"),
        ]


class OrganizationVerification(OrganizationRecord):
    """T16: expediente privado; la resolución requiere el procedimiento autorizado."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        WITHDRAWN = "withdrawn", "Retirada"

    organization = models.ForeignKey(
        Organization, on_delete=models.RESTRICT, related_name="verifications", db_index=False
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="requested_by",
        on_delete=models.RESTRICT,
        related_name="organization_verification_requests",
        db_index=False,
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_default="pending"
    )
    evidence_reference = models.TextField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="organization_verification_decisions",
        null=True,
        blank=True,
        db_index=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "organizations_verification"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "approved", "rejected", "withdrawn"]),
                name="ck_t16_01",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", decided_at__isnull=True, decided_by__isnull=True)
                    | (~models.Q(status="pending") & models.Q(decided_at__isnull=False))
                ),
                name="ck_t16_02",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending")
                    | (
                        models.Q(decided_by__isnull=False, decision_reason__isnull=False)
                        & GreaterThan(Length(Trim("decision_reason")), models.Value(0))
                    )
                ),
                name="ck_t16_03",
            ),
            models.UniqueConstraint(
                fields=["organization"], condition=models.Q(status="pending"), name="uq_t16_01"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="ix_t16_02"),
            models.Index(fields=["requested_by"], name="ix_t16_03"),
            models.Index(fields=["decided_by"], name="ix_t16_04"),
        ]


class Representation(OrganizationRecord):
    """T17: iguales facultades entre representantes, sin rangos ni verificación personal."""

    organization = models.ForeignKey(
        Organization, on_delete=models.RESTRICT, related_name="representations", db_index=False
    )
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="organization_representations",
        db_index=False,
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="granted_by",
        on_delete=models.RESTRICT,
        related_name="granted_representations",
        db_index=False,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="revoked_by",
        on_delete=models.RESTRICT,
        related_name="revoked_representations",
        null=True,
        blank=True,
        db_index=False,
    )
    revocation_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "organizations_representation"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(revoked_at__isnull=True, revoked_by__isnull=True)
                    | models.Q(revoked_at__isnull=False, revoked_by__isnull=False)
                ),
                name="ck_t17_01",
            ),
            models.CheckConstraint(
                condition=models.Q(revoked_at__isnull=True)
                | models.Q(revoked_at__gte=models.F("created_at")),
                name="ck_t17_02",
            ),
            models.UniqueConstraint(
                fields=["organization", "account"],
                condition=models.Q(revoked_at__isnull=True),
                name="uq_t17_01",
            ),
        ]
        indexes = [
            models.Index(fields=["organization"], name="ix_t17_02"),
            models.Index(fields=["account"], name="ix_t17_03"),
            models.Index(fields=["granted_by"], name="ix_t17_04"),
            models.Index(fields=["revoked_by"], name="ix_t17_05"),
        ]
