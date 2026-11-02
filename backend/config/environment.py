"""Lectura de variables de proceso sin registrar sus valores."""

import os

from django.core.exceptions import ImproperlyConfigured


def env_string(name, default="", *, required=False):
    value = os.environ.get(name, default)
    if required and not value.strip():
        raise ImproperlyConfigured(f"Falta configurar {name}.")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ImproperlyConfigured(f"{name} debe ser un booleano válido.")


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def database_port():
    try:
        port = int(env_string("POSTGRES_PORT", "5432"))
    except ValueError as error:
        raise ImproperlyConfigured("POSTGRES_PORT debe ser un puerto válido.") from error
    if not 1 <= port <= 65535:
        raise ImproperlyConfigured("POSTGRES_PORT debe ser un puerto válido.")
    return port
