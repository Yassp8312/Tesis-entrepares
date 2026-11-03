"""Protección del destino de pruebas antes de crear o borrar una base."""

import os

import psycopg
import pytest
from django.conf import settings
from django.db import connection
from psycopg import sql


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings):
    database = settings.DATABASES["default"]
    expected = os.environ.get("POSTGRES_TEST_CLUSTER_NAME", "")
    if (
        settings.SETTINGS_MODULE != "config.settings.test"
        or database["ENGINE"] != "django.db.backends.postgresql"
        or database["HOST"] != "127.0.0.1"
        or database["USER"] != "entrepares_test"
        or database["NAME"] != "entrepares_test"
        or database["TEST"]["NAME"] != "test_entrepares"
        or not database["PASSWORD"]
        or not expected.startswith("entrepares-local-")
    ):
        raise pytest.UsageError(
            "El destino no es el entorno aislado previsto; usa scripts/probar.ps1."
        )
    try:
        with psycopg.connect(
            host=database["HOST"],
            port=database["PORT"],
            user=database["USER"],
            password=database["PASSWORD"],
            dbname=database["NAME"],
            connect_timeout=5,
        ) as preflight:
            cluster, version = preflight.execute(
                "SELECT current_setting('cluster_name'), current_setting('server_version_num')"
            ).fetchone()
            if cluster != expected or not 170000 <= int(version) < 180000:
                raise pytest.UsageError("El servidor no es el cluster PostgreSQL 17 esperado.")
    except psycopg.Error:
        raise pytest.UsageError(
            "No se pudo comprobar el cluster privado; inicia PostgreSQL del proyecto."
        ) from None


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    # Tras crear la base efímera, su propietario elimina CONNECT concedido a PUBLIC.
    with django_db_blocker.unblock():
        name = connection.settings_dict["NAME"]
        if name != "test_entrepares":
            raise pytest.UsageError(
                "No se modifican permisos de una base distinta de la de pruebas."
            )
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
            )
    yield
