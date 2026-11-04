"""T32–T33: catálogo y concesiones; los permisos efectivos se evalúan al operar."""

import uuid

from django.conf import settings
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class Capability(models.Model):
    """T32: describir una capacidad no se la concede a ninguna cuenta."""

    code = models.CharField(max_length=80, primary_key=True)
    description = models.TextField()
    is_delegable = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = "access_capability"
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("code")), models.Value(0)), name="ck_t32_01"
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("description")), models.Value(0)),
                name="ck_t32_02",
            ),
        ]

    def __str__(self):
        return self.code


class Grant(models.Model):
    """T33: la FK compuesta exige que la concesión fuente pertenezca al otorgante."""

    class ScopeKind(models.TextChoices):
        GLOBAL = "global", "Global"
        ACADEMIC = "academic", "Académico"
        ORGANIZATION = "organization", "Organizacional"

    class Source(models.TextChoices):
        BOOTSTRAP = "bootstrap", "Habilitación inicial"
        DELEGATION = "delegation", "Delegación"
        ADMINISTRATIVE = "administrative", "Administrativa"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="capability_grants",
        db_index=False,
    )
    capability = models.ForeignKey(
        Capability,
        db_column="capability_code",
        on_delete=models.RESTRICT,
        related_name="grants",
        db_index=False,
    )
    scope_kind = models.CharField(max_length=16, choices=ScopeKind.choices)
    academic_scope = models.ForeignKey(
        "academics.AcademicScope",
        on_delete=models.RESTRICT,
        related_name="capability_grants",
        null=True,
        blank=True,
        db_index=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.RESTRICT,
        related_name="capability_grants",
        null=True,
        blank=True,
        db_index=False,
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="granted_by",
        on_delete=models.RESTRICT,
        related_name="issued_capability_grants",
        db_index=False,
    )
    parent_grant = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        related_name="child_grants",
        null=True,
        blank=True,
        db_index=False,
        db_constraint=False,
    )
    source = models.CharField(max_length=24, choices=Source.choices)
    valid_from = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    valid_until = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="ended_by",
        on_delete=models.RESTRICT,
        related_name="ended_capability_grants",
        null=True,
        blank=True,
        db_index=False,
    )
    end_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    updated_at = models.DateTimeField(auto_now=True, db_default=TransactionNow())

    class Meta:
        db_table = "access_grant"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scope_kind__in=["global", "academic", "organization"]),
                name="ck_t33_01",
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=["bootstrap", "delegation", "administrative"]),
                name="ck_t33_02",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        scope_kind="global", academic_scope__isnull=True, organization__isnull=True
                    )
                    | models.Q(
                        scope_kind="academic",
                        academic_scope__isnull=False,
                        organization__isnull=True,
                    )
                    | models.Q(
                        scope_kind="organization",
                        academic_scope__isnull=True,
                        organization__isnull=False,
                    )
                ),
                name="ck_t33_03",
            ),
            models.CheckConstraint(
                condition=models.Q(parent_grant__isnull=True)
                | ~models.Q(parent_grant=models.F("id")),
                name="ck_t33_04",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="ck_t33_05",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True, ended_by__isnull=True)
                | models.Q(ended_at__isnull=False, ended_by__isnull=False),
                name="ck_t33_06",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | (
                    models.Q(end_reason__isnull=False)
                    & GreaterThan(Length(Trim("end_reason")), models.Value(0))
                ),
                name="ck_t33_07",
            ),
            models.UniqueConstraint(fields=["id", "account"], name="uq_t33_key01"),
            models.UniqueConstraint(
                fields=["account", "capability", "scope_kind", "academic_scope", "organization"],
                condition=models.Q(ended_at__isnull=True),
                nulls_distinct=False,
                name="uq_t33_01",
            ),
        ]
        indexes = [
            models.Index(fields=["account"], name="ix_t33_02"),
            models.Index(fields=["granted_by"], name="ix_t33_03"),
            models.Index(fields=["ended_by"], name="ix_t33_04"),
            models.Index(fields=["capability"], name="ix_t33_05"),
            models.Index(fields=["academic_scope"], name="ix_t33_06"),
            models.Index(fields=["organization"], name="ix_t33_07"),
            models.Index(fields=["parent_grant", "granted_by"], name="ix_t33_08"),
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)
