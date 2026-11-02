"""T01 Cuenta, independiente de perfiles, respaldos y moderación."""

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
