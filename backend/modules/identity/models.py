"""T01–T03: cuenta, metadatos de comprobación y alegación de recuperación."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.password_validation import validate_password
from django.contrib.postgres.functions import RandomUUID, TransactionNow
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Length, Lower, Trim
from django.db.models.lookups import GreaterThan
from django.utils import timezone


class AccountManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.alias(email_identity=Lower("email")).get(
            email_identity=Lower(models.Value(username.strip()))
        )

    async def aget_by_natural_key(self, username):
        return await self.alias(email_identity=Lower("email")).aget(
            email_identity=Lower(models.Value(username.strip()))
        )

    def _create_user(self, email, password, **extra_fields):
        if not isinstance(email, str):
            raise ValueError("Debe indicar un correo de acceso.")
        email = self.model._meta.get_field("email").clean(email.strip(), None)
        user = self.model(email=email, **extra_fields)
        if password is not None:
            if not isinstance(password, str) or not password.strip() or len(password) > 128:
                raise ValidationError("La contraseña no cumple el formato admitido.")
            validate_password(password, user)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        if extra_fields["is_staff"] or extra_fields["is_superuser"]:
            raise ValueError("La creación ordinaria no admite privilegios técnicos.")
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("El superusuario técnico requiere ambas banderas.")
        if password is None:
            raise ValueError("El superusuario técnico requiere contraseña.")
        return self._create_user(email, password, **extra_fields)


class Account(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    email = models.EmailField(max_length=254)
    is_active = models.BooleanField(default=True, db_default=True)
    is_staff = models.BooleanField(default=False, db_default=False)
    is_superuser = models.BooleanField(default=False, db_default=False)
    date_joined = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    updated_at = models.DateTimeField(auto_now=True, db_default=TransactionNow())

    objects = AccountManager()
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "identity_account"
        verbose_name = "cuenta"
        verbose_name_plural = "cuentas"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uq_t01_01"),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("email")), models.Value(0)),
                name="ck_t01_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("password")), models.Value(0)),
                name="ck_t01_02",
            ),
        ]

    def clean(self):
        # Se conserva la escritura de la dirección para entrega; no se fuerza a minúsculas.
        if isinstance(self.email, str):
            self.email = self.email.strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)


class EmailChallenge(models.Model):
    """T02: metadatos; la firma y su clave se mantienen fuera de la tabla."""

    class Purpose(models.TextChoices):
        EMAIL_CONFIRMATION = "email_confirmation", "Confirmación de correo"
        PASSWORD_RESET = "password_reset", "Restablecimiento de contraseña"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="email_challenges", db_index=False
    )
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    email_snapshot = models.EmailField(max_length=254)
    key_version = models.CharField(max_length=32, default="v1", db_default="v1")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = "identity_email_challenge"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=["email_confirmation", "password_reset"]),
                name="ck_t02_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("email_snapshot")), models.Value(0)),
                name="ck_t02_02",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("key_version")), models.Value(0)),
                name="ck_t02_03",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="ck_t02_04",
            ),
            models.CheckConstraint(
                condition=~models.Q(consumed_at__isnull=False, invalidated_at__isnull=False),
                name="ck_t02_05",
            ),
            models.UniqueConstraint(fields=["id", "account"], name="uq_t02_key01"),
        ]
        indexes = [models.Index(fields=["account", "purpose", "expires_at"], name="ix_t02_01")]

    def __str__(self):
        return str(self.pk)


class RecoveryRequest(models.Model):
    """T03: registrar o resolver la alegación no autentica ni verifica a nadie."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_default=RandomUUID(), editable=False
    )
    claimed_email = models.EmailField(max_length=254)
    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name="recovery_requests",
        null=True,
        blank=True,
        db_index=False,
    )
    reply_contact = models.TextField(null=True, blank=True)
    statement = models.TextField()
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING, db_default="pending"
    )
    decided_by = models.ForeignKey(
        Account,
        db_column="decided_by",
        on_delete=models.RESTRICT,
        related_name="recovery_decisions",
        null=True,
        blank=True,
        db_index=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())
    updated_at = models.DateTimeField(auto_now=True, db_default=TransactionNow())

    class Meta:
        db_table = "identity_recovery_request"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "approved", "rejected"]),
                name="ck_t03_01",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("claimed_email")), models.Value(0)),
                name="ck_t03_02",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("statement")), models.Value(0)),
                name="ck_t03_03",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", decided_at__isnull=True, decided_by__isnull=True)
                    | (
                        ~models.Q(status="pending")
                        & models.Q(
                            decided_at__isnull=False,
                            decided_by__isnull=False,
                            decision_reason__isnull=False,
                        )
                        & GreaterThan(Length(Trim("decision_reason")), models.Value(0))
                    )
                ),
                name="ck_t03_04",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="approved") | models.Q(account__isnull=False),
                name="ck_t03_05",
            ),
        ]
        indexes = [
            models.Index(fields=["account"], name="ix_t03_01"),
            models.Index(fields=["decided_by"], name="ix_t03_02"),
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)
