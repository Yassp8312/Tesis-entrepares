"""La herramienta destructiva de reproducción debe rechazar destinos ajenos."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.db import connection
from psycopg import sql

from tests.support.factories import SyntheticFactory
from tests.support.schema import inspect_schema, load_reference

ROOT = Path(__file__).resolve().parents[2]


def run_tool(output, changes=None):
    environment = os.environ.copy()
    environment.update(changes or {})
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/comprobar_migraciones.py"), "--output", str(output)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"POSTGRES_HOST": "192.0.2.1"},
        {"POSTGRES_TEST_USER": "entrepares_dev"},
        {"POSTGRES_TEST_DB": "entrepares_development"},
        {"POSTGRES_TEST_DB_NAME": "entrepares_development"},
        {"POSTGRES_TEST_PASSWORD": ""},
        {"POSTGRES_TEST_CLUSTER_NAME": "otro-cluster"},
    ],
)
def test_reproduction_refuses_incorrect_destination_before_connecting(tmp_path, changes):
    # Los demás valores válidos no necesitan ser credenciales utilizables:
    # cada variante debe fallar en la guarda anterior a psycopg.connect.
    environment = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_TEST_USER": "entrepares_test",
        "POSTGRES_TEST_DB": "entrepares_test",
        "POSTGRES_TEST_DB_NAME": "test_entrepares",
        "POSTGRES_TEST_PASSWORD": "synthetic-unusable-password",
        "POSTGRES_TEST_CLUSTER_NAME": "entrepares-local-synthetic",
        **changes,
    }
    output = tmp_path / "refused.json"
    result = run_tool(output, environment)
    assert result.returncode != 0
    assert "El destino no es el entorno aislado previsto." in result.stderr
    assert not output.exists()


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_reproduction_preserves_existing_database_schema_history_and_corpus(tmp_path):
    SyntheticFactory().build_graph()
    reference = load_reference()

    def snapshot():
        with connection.cursor() as cursor:
            cursor.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
            database_oid = cursor.fetchone()[0]
            cursor.execute("SELECT app,name,applied FROM django_migrations ORDER BY app,name")
            history = cursor.fetchall()
            # Identificadores del contrato estructural cerrado; no datos reales.
            rows = {}
            for table in reference["tables"]:
                cursor.execute(
                    sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(
                        sql.Identifier(table["name"])
                    )
                )
                rows[table["id"]] = cursor.fetchall()
        return database_oid, history, rows, inspect_schema(connection, reference)

    before = snapshot()
    output = tmp_path / "refused-existing.json"
    result = run_tool(output)
    assert result.returncode != 0
    assert "La base efímera ya existe; no se reutiliza, modifica o elimina." in result.stderr
    assert not output.exists()
    assert snapshot() == before
