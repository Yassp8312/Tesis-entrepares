"""T37: evidencia mínima; las proyecciones se preparan en la interfaz propietaria."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import Exact, GreaterThan
from django.utils import timezone


class AuditEvent(models.Model):
    class ActorKind(models.TextChoices):
        ACCOUNT = "account", "Cuenta"
        SYSTEM = "system", "Sistema"

    class ContextKind(models.TextChoices):
        PERSONAL = "personal", "Personal"
        ORGANIZATION = "organization", "Organizacional"
        SYSTEM = "system", "Sistema"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    actor_kind = models.CharField(max_length=16, choices=ActorKind.choices)
    actor_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_index=False,
    )
    context_kind = models.CharField(max_length=16, choices=ContextKind.choices)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.RESTRICT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_index=False,
    )
    academic_scope = models.ForeignKey(
        "academics.AcademicScope",
        on_delete=models.RESTRICT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_index=False,
    )
    action_code = models.CharField(max_length=80)
    resource_kind = models.CharField(max_length=80)
    resource_id = models.UUIDField()
    occurred_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    reason = models.TextField(null=True, blank=True)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    correlation_id = models.UUIDField()

    class Meta:
        db_table = "audit_event"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(actor_kind__in=["account", "system"]), name="ck_t37_01"
            ),
            models.CheckConstraint(
                condition=models.Q(context_kind__in=["personal", "organization", "system"]),
                name="ck_t37_02",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("action_code")), models.Value(0)),
                name="ck_t37_03",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("resource_kind")), models.Value(0)),
                name="ck_t37_04",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(actor_kind="system", actor_account__isnull=True, context_kind="system")
                    | (
                        models.Q(actor_kind="account", actor_account__isnull=False)
                        & ~models.Q(context_kind="system")
                    )
                ),
                name="ck_t37_05",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(context_kind="organization", organization__isnull=False)
                    | (~models.Q(context_kind="organization") & models.Q(organization__isnull=True))
                ),
                name="ck_t37_06",
            ),
            models.CheckConstraint(
                condition=models.Q(before_state__isnull=True)
                | Exact(
                    models.Func(
                        models.F("before_state"),
                        function="jsonb_typeof",
                        output_field=models.CharField(),
                    ),
                    models.Value("object"),
                ),
                name="ck_t37_07",
            ),
            models.CheckConstraint(
                condition=models.Q(after_state__isnull=True)
                | Exact(
                    models.Func(
                        models.F("after_state"),
                        function="jsonb_typeof",
                        output_field=models.CharField(),
                    ),
                    models.Value("object"),
                ),
                name="ck_t37_08",
            ),
        ]
        indexes = [
            models.Index(fields=["resource_kind", "resource_id", "occurred_at"], name="ix_t37_01"),
            models.Index(fields=["actor_account", "occurred_at"], name="ix_t37_02"),
            models.Index(fields=["correlation_id"], name="ix_t37_03"),
            models.Index(fields=["organization"], name="ix_t37_04"),
            models.Index(fields=["academic_scope"], name="ix_t37_05"),
        ]

    def __str__(self):
        return str(self.pk)
