"""T26–T31: reportes, decisiones, medidas y revisión de la propia persona afectada."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class CreatedRecord(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.pk)


class MutableRecord(CreatedRecord):
    updated_at = models.DateTimeField(auto_now=True, db_default=TransactionNow())

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        return super().save(*args, **kwargs)


class Report(CreatedRecord):
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.RESTRICT,
        related_name="moderation_reports",
        null=True,
        blank=True,
        db_index=False,
    )
    publication = models.ForeignKey(
        "publications.Publication",
        on_delete=models.RESTRICT,
        related_name="moderation_reports",
        null=True,
        blank=True,
        db_index=False,
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="reported_by",
        on_delete=models.RESTRICT,
        related_name="submitted_reports",
        db_index=False,
    )
    reason = models.TextField()

    class Meta:
        db_table = "moderation_report"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(opportunity__isnull=True, publication__isnull=False)
                | models.Q(opportunity__isnull=False, publication__isnull=True),
                name="ck_t26_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("reason")), models.Value(0)), name="ck_t26_02"
            ),
        ]
        indexes = [
            models.Index(fields=["opportunity"], name="ix_t26_01"),
            models.Index(fields=["publication"], name="ix_t26_02"),
            models.Index(fields=["reported_by"], name="ix_t26_03"),
        ]


class Decision(CreatedRecord):
    class Outcome(models.TextChoices):
        VIOLATION = "violation", "Infracción"
        NO_VIOLATION = "no_violation", "Sin infracción"

    class ContentAction(models.TextChoices):
        NONE = "none", "Ninguna"
        HIDE = "hide", "Ocultar"
        REMOVE = "remove", "Retirar"

    report = models.ForeignKey(
        Report, on_delete=models.RESTRICT, related_name="decisions", db_index=False
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="moderation_decisions",
        db_index=False,
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.TextField()
    content_action = models.CharField(max_length=16, choices=ContentAction.choices)

    class Meta:
        db_table = "moderation_decision"
        constraints = [
            models.UniqueConstraint(fields=["report"], name="uq_t27_key01"),
            models.CheckConstraint(
                condition=models.Q(outcome__in=["violation", "no_violation"]), name="ck_t27_01"
            ),
            models.CheckConstraint(
                condition=models.Q(content_action__in=["none", "hide", "remove"]), name="ck_t27_02"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("reason")), models.Value(0)), name="ck_t27_03"
            ),
            models.CheckConstraint(
                condition=~models.Q(outcome="no_violation") | models.Q(content_action="none"),
                name="ck_t27_04",
            ),
        ]
        indexes = [models.Index(fields=["decided_by"], name="ix_t27_01")]


class Measure(MutableRecord):
    class Kind(models.TextChoices):
        WARNING = "warning", "Advertencia"
        BAN = "ban", "Bloqueo"

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="moderation_measures",
        db_index=False,
    )
    source_decision = models.ForeignKey(
        Decision, on_delete=models.RESTRICT, related_name="measures", db_index=False
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    starts_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    ends_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="revoked_by",
        on_delete=models.RESTRICT,
        related_name="revoked_moderation_measures",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "moderation_measure"
        constraints = [
            models.UniqueConstraint(fields=["id", "account"], name="uq_t28_key01"),
            models.CheckConstraint(
                condition=models.Q(kind__in=["warning", "ban"]), name="ck_t28_01"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_t28_02",
            ),
            models.CheckConstraint(
                condition=models.Q(revoked_at__isnull=True, revoked_by__isnull=True)
                | models.Q(revoked_at__isnull=False, revoked_by__isnull=False),
                name="ck_t28_03",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind="warning") | models.Q(ends_at__isnull=True),
                name="ck_t28_04",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "starts_at"], name="ix_t28_01"),
            models.Index(fields=["source_decision"], name="ix_t28_02"),
            models.Index(fields=["revoked_by"], name="ix_t28_03"),
        ]


class Restriction(MutableRecord):
    class ContextKind(models.TextChoices):
        PERSONAL = "personal", "Personal"
        ORGANIZATION = "organization", "Organizacional"
        BOTH = "both", "Ambos"

    measure = models.ForeignKey(
        Measure, on_delete=models.RESTRICT, related_name="restrictions", db_index=False
    )
    capability = models.ForeignKey(
        "access.Capability",
        db_column="capability_code",
        on_delete=models.RESTRICT,
        related_name="moderation_restrictions",
        db_index=False,
    )
    context_kind = models.CharField(max_length=16, choices=ContextKind.choices)

    class Meta:
        db_table = "moderation_restriction"
        constraints = [
            models.UniqueConstraint(
                fields=["measure", "capability", "context_kind"], name="uq_t29_key01"
            ),
            models.CheckConstraint(
                condition=models.Q(context_kind__in=["personal", "organization", "both"]),
                name="ck_t29_01",
            ),
            models.CheckConstraint(
                condition=~models.Q(capability="moderation.request_review"), name="ck_t29_02"
            ),
        ]
        indexes = [models.Index(fields=["capability"], name="ix_t29_01")]


class ReviewRequest(CreatedRecord):
    """La FK compuesta vincula measure/requested_by con id/account_id de la medida."""

    measure = models.ForeignKey(
        Measure,
        on_delete=models.RESTRICT,
        related_name="review_requests",
        db_index=False,
        db_constraint=False,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="requested_by",
        on_delete=models.RESTRICT,
        related_name="moderation_review_requests",
        db_index=False,
        db_constraint=False,
    )
    reason = models.TextField()

    class Meta:
        db_table = "moderation_review_request"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("reason")), models.Value(0)), name="ck_t30_01"
            )
        ]
        indexes = [models.Index(fields=["measure", "requested_by"], name="ix_t30_01")]


class ReviewDecision(CreatedRecord):
    class Outcome(models.TextChoices):
        UPHELD = "upheld", "Ratificada"
        REVOKED = "revoked", "Revocada"
        REPLACED = "replaced", "Sustituida"

    request = models.ForeignKey(
        ReviewRequest, on_delete=models.RESTRICT, related_name="decisions", db_index=False
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="moderation_review_decisions",
        db_index=False,
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.TextField()
    replacement_measure = models.ForeignKey(
        Measure,
        on_delete=models.RESTRICT,
        related_name="replacement_decisions",
        null=True,
        blank=True,
        db_index=False,
    )

    class Meta:
        db_table = "moderation_review_decision"
        constraints = [
            models.UniqueConstraint(fields=["request"], name="uq_t31_key01"),
            models.UniqueConstraint(fields=["replacement_measure"], name="uq_t31_key02"),
            models.CheckConstraint(
                condition=models.Q(outcome__in=["upheld", "revoked", "replaced"]), name="ck_t31_01"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("reason")), models.Value(0)), name="ck_t31_02"
            ),
            models.CheckConstraint(
                condition=models.Q(outcome="replaced", replacement_measure__isnull=False)
                | (~models.Q(outcome="replaced") & models.Q(replacement_measure__isnull=True)),
                name="ck_t31_03",
            ),
        ]
        indexes = [models.Index(fields=["decided_by"], name="ix_t31_01")]
