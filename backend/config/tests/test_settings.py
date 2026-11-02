import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

BACKEND = Path(__file__).resolve().parents[2]


def production_process(overrides=None, missing=()):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "POSTGRES_", "EMAIL_"))
    }
    environment.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DJANGO_SECRET_KEY="clave-sintetica-para-probar-la-configuracion-de-produccion-" * 2,
        DJANGO_ALLOWED_HOSTS="plataforma.example.org",
        POSTGRES_DB="base_sintetica",
        POSTGRES_USER="usuario_sintetico",
        POSTGRES_PASSWORD="valor-sintetico-sin-uso-real",
        POSTGRES_HOST="db.example.invalid",
        PYTHONIOENCODING="utf-8",
    )
    environment.update(overrides or {})
    for key in missing:
        environment.pop(key, None)
    code = """
import json
import django
django.setup()
from django.conf import settings
from django.db import connection
print(json.dumps({
    'debug': settings.DEBUG,
    'secure_session': settings.SESSION_COOKIE_SECURE,
    'secure_csrf': settings.CSRF_COOKIE_SECURE,
    'https_redirect': settings.SECURE_SSL_REDIRECT,
    'user': settings.AUTH_USER_MODEL,
    'engine': settings.DATABASES['default']['ENGINE'],
    'connection_open': connection.connection is not None,
    'proxy_ssl': settings.SECURE_PROXY_SSL_HEADER,
}))
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def test_test_environment_keeps_postgresql_and_csrf():
    assert settings.AUTH_USER_MODEL == "identity.Account"
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "rest_framework.authentication.SessionAuthentication"
    ]


@pytest.mark.parametrize("technical_superuser", [False, True])
def test_unconfigured_api_denies_access_even_to_technical_superuser(technical_superuser):
    from rest_framework.response import Response
    from rest_framework.test import APIRequestFactory, force_authenticate
    from rest_framework.views import APIView

    from modules.identity.models import Account

    class UnconfiguredView(APIView):
        def get(self, request):
            return Response({"dato_que_no_debe_exponerse": True})

    request = APIRequestFactory().get("/ruta-sintetica-sin-registrar/")
    if technical_superuser:
        force_authenticate(request, user=Account(is_staff=True, is_superuser=True))
    response = UnconfiguredView.as_view()(request)
    assert response.status_code == 403
    assert "dato_que_no_debe_exponerse" not in response.data


def test_production_ignores_debug_request_and_requires_https():
    process = production_process({"DJANGO_DEBUG": "true"})
    assert process.returncode == 0, process.stderr
    actual = json.loads(process.stdout)
    assert actual == {
        "debug": False,
        "secure_session": True,
        "secure_csrf": True,
        "https_redirect": True,
        "user": "identity.Account",
        "engine": "django.db.backends.postgresql",
        "connection_open": False,
        "proxy_ssl": None,
    }


@pytest.mark.parametrize(
    "missing",
    [
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
    ],
)
def test_production_fails_without_explicit_configuration(missing):
    process = production_process(missing=[missing])
    assert process.returncode != 0
    assert missing in process.stderr
    assert "valor-sintetico-sin-uso-real" not in process.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"DJANGO_ALLOWED_HOSTS": "*"},
        {"DJANGO_SECRET_KEY": "test-only-" + "x" * 64},
        {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://plataforma.example.org"},
        {"POSTGRES_PORT": "incorrecto"},
    ],
)
def test_production_rejects_unsafe_or_invalid_values(overrides):
    assert production_process(overrides).returncode != 0
