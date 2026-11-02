"""Guarda la unicidad funcional que sustituye al chequeo genérico auth.W004."""

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import models
from django.db.models.functions import Lower


@register(Tags.models)
def check_account_identity(app_configs=None, **kwargs):
    account = apps.get_model(settings.AUTH_USER_MODEL)
    expected = models.UniqueConstraint(Lower("email"), name="uq_t01_01")
    if (
        account._meta.label_lower != "identity.account"
        or account.USERNAME_FIELD != "email"
        or expected not in account._meta.constraints
    ):
        return [
            Error(
                "La identidad de acceso requiere identity.Account y unicidad de lower(email).",
                id="identity.E001",
            )
        ]
    return []
