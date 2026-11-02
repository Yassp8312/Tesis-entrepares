"""Ajustes explícitos de prueba; nunca se utilizan como configuración WSGI."""

import os

from config.environment import env_string

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-entrepares-" + "x" * 64)

from .base import *  # noqa: E402,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES["default"].update(  # noqa: F405
    NAME=env_string("POSTGRES_TEST_DB", "entrepares_test"),
    USER=env_string("POSTGRES_TEST_USER", "entrepares_test"),
    PASSWORD=env_string("POSTGRES_TEST_PASSWORD"),
    TEST={"NAME": env_string("POSTGRES_TEST_DB_NAME", "test_entrepares")},
)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
