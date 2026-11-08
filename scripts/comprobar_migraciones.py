"""Reconstruye solo una base efímera nueva; rechaza reutilizar una existente.

Ejecutar con el entorno fijado del proyecto. No sirve para migrar desarrollo o
producción. La reversión total destruye únicamente el corpus sintético creado
por esta ejecución; no es un procedimiento de restauración de datos.
"""

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
TARGET = "test_entrepares"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def inventory(connection):
    with connection.cursor() as cursor:
        tables = sorted(connection.introspection.table_names(cursor))
        cursor.execute("SELECT viewname FROM pg_views WHERE schemaname=current_schema() ORDER BY 1")
        views = [row[0] for row in cursor]
    return {"tables": tables, "views": views}


def data_fingerprint(connection, reference):
    fingerprints = {}
    with connection.cursor() as cursor:
        for table in reference["tables"]:
            cursor.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(table["name"]))
            )
            rows = cursor.fetchall()
            fingerprints[table["id"]] = {"count": len(rows), "sha256": digest(rows)}
    return fingerprints


def exercise(connection):
    from django.core.management import call_command
    from django.db.migrations.executor import MigrationExecutor

    from tests.support.factories import SyntheticFactory
    from tests.support.schema import inspect_schema, load_reference, schema_report

    reference = load_reference()
    initial = inventory(connection)
    require(initial == {"tables": [], "views": []}, "La base recién creada no está vacía.")
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    order = [
        {
            "app": migration.app_label,
            "name": migration.name,
            "dependencies": [list(dependency) for dependency in migration.dependencies],
            "operations_reversible": all(op.reversible for op in migration.operations),
        }
        for migration, backwards in plan
        if not backwards
    ]
    require(order and all(m["operations_reversible"] for m in order), "Plan no reversible.")
    log = io.StringIO()
    call_command("migrate", interactive=False, verbosity=1, stdout=log, no_color=True)
    installed = schema_report(connection)
    require(installed["matched"], "El esquema recién instalado difiere de la referencia.")
    with connection.cursor() as cursor:
        for table in reference["tables"]:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table["name"])))
            require(cursor.fetchone()[0] == 0, "La instalación introdujo datos de negocio.")

    SyntheticFactory().build_graph()
    structure_before = digest(inspect_schema(connection, reference))
    rows_before = data_fingerprint(connection, reference)
    with connection.cursor() as cursor:
        cursor.execute("SELECT app,name,applied FROM django_migrations ORDER BY app,name")
        records_before = cursor.fetchall()
    second_plan = MigrationExecutor(connection).migration_plan(
        MigrationExecutor(connection).loader.graph.leaf_nodes()
    )
    second_log = io.StringIO()
    call_command("migrate", interactive=False, verbosity=1, stdout=second_log, no_color=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT app,name,applied FROM django_migrations ORDER BY app,name")
        records_after = cursor.fetchall()
    unchanged = (
        not second_plan
        and structure_before == digest(inspect_schema(connection, reference))
        and rows_before == data_fingerprint(connection, reference)
        and records_before == records_after
    )
    require(unchanged, "La segunda aplicación alteró esquema, datos o historial de migraciones.")

    # Solo el destino recién creado por main: ninguna opción de esta herramienta
    # permite revertir una base que ya existiera al comenzar.
    executor = MigrationExecutor(connection)
    executor.migrate([(app, None) for app in sorted(executor.loader.migrated_apps)])
    reverted = inventory(connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM django_migrations")
        remaining = cursor.fetchone()[0]
    require(
        reverted == {"tables": ["django_migrations"], "views": []} and remaining == 0,
        "La reversión no retiró todo el esquema salvo el registro técnico vacío.",
    )
    call_command("migrate", interactive=False, verbosity=0, stdout=io.StringIO())
    reapplied = schema_report(connection)
    require(reapplied["matched"], "La reaplicación después de revertir difiere de la referencia.")
    return {
        "empty_database": initial,
        "migration_order": order,
        "applied_migrations": len(records_before),
        "installed": {
            "matched": installed["matched"],
            "counts": installed["counts"],
            "business_rows_before_corpus": 0,
            "predicate_cases": sum(p["cases"] for p in installed["predicates"]),
        },
        "second_application": {
            "plan": second_plan,
            "unchanged": unchanged,
            "schema_sha256": structure_before,
            "synthetic_rows_by_table": {key: item["count"] for key, item in rows_before.items()},
            "synthetic_data_sha256": digest(rows_before),
            "migration_history_sha256": digest(records_before),
            "output": second_log.getvalue().splitlines(),
        },
        "reverse_all": {"inventory": reverted, "applied_migrations": remaining},
        "reapply": {"matched": reapplied["matched"], "counts": reapplied["counts"]},
        "limits": [
            "Reversión total destructiva solo sobre corpus sintético efímero.",
            "La reconstrucción del esquema no restaura los datos retirados.",
            "No prueba backup, actualización de una versión futura, piloto o correos reales.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    import django

    django.setup()
    from django.db import connection

    database = connection.settings_dict
    expected = os.environ.get("POSTGRES_TEST_CLUSTER_NAME", "")
    require(
        database["ENGINE"] == "django.db.backends.postgresql"
        and (database["HOST"], database["USER"], database["NAME"], database["TEST"]["NAME"])
        == ("127.0.0.1", "entrepares_test", "entrepares_test", TARGET)
        and bool(database["PASSWORD"])
        and expected.startswith("entrepares-local-"),
        "El destino no es el entorno aislado previsto.",
    )
    connection.close()
    report = None
    with psycopg.connect(
        host=database["HOST"],
        port=database["PORT"],
        user=database["USER"],
        password=database["PASSWORD"],
        dbname=database["NAME"],
        connect_timeout=5,
        autocommit=True,
    ) as bootstrap:
        cluster, version, role, name = bootstrap.execute(
            "SELECT current_setting('cluster_name'), current_setting('server_version_num'), "
            "current_user, current_database()"
        ).fetchone()
        require(
            cluster == expected
            and 170000 <= int(version) < 180000
            and role == "entrepares_test"
            and name == "entrepares_test",
            "El servidor no es el cluster PostgreSQL 17 privado esperado.",
        )
        require(
            bootstrap.execute("SELECT oid FROM pg_database WHERE datname=%s", (TARGET,)).fetchone()
            is None,
            "La base efímera ya existe; no se reutiliza, modifica o elimina.",
        )
        bootstrap.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(TARGET), sql.Identifier(role)
            )
        )
        created_oid = bootstrap.execute(
            "SELECT oid FROM pg_database WHERE datname=%s", (TARGET,)
        ).fetchone()[0]
        try:
            bootstrap.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(TARGET))
            )
            database["NAME"] = TARGET
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_user, current_setting('cluster_name')"
                )
                require(cursor.fetchone() == (TARGET, role, expected), "Destino inesperado.")
            report = exercise(connection)
        finally:
            connection.close()
            current = bootstrap.execute(
                "SELECT oid,pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (TARGET,)
            ).fetchone()
            require(
                current == (created_oid, role), "Cambió la identidad de la base; no se elimina."
            )
            # Sin FORCE, sin terminar sesiones ajenas y sin borrar rutas del disco.
            bootstrap.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(TARGET)))
        report["temporary_database_removed"] = (
            bootstrap.execute("SELECT 1 FROM pg_database WHERE datname=%s", (TARGET,)).fetchone()
            is None
        )
    report["executed_at_utc"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "installation": True,
                "second_application_unchanged": True,
                "reverse_and_reapply": True,
                "temporary_database_removed": True,
            }
        )
    )


if __name__ == "__main__":
    main()
