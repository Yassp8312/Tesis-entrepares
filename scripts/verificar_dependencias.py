"""Comprueba el entorno Python sin crear tablas ni conectar con una base."""

import importlib.metadata
import json
import platform
import sys
import tomllib
from pathlib import Path

import django
import psycopg
import rest_framework
from django.conf import settings

ROOT = Path(__file__).resolve().parents[1]
expected_python = ROOT.joinpath(".python-version").read_text(encoding="utf-8").strip()
if platform.python_version() != expected_python:
    raise SystemExit(
        f"Se esperaba Python {expected_python}; se encontró {platform.python_version()}."
    )

manifest = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
versions = {}
for specification in manifest["project"]["dependencies"]:
    requirement, _, marker = specification.partition(";")
    if marker and sys.platform == "win32":
        continue
    name, expected = requirement.strip().split("==")
    name = name.split("[")[0]
    actual = importlib.metadata.version(name)
    if actual != expected:
        raise SystemExit(f"Se esperaba {name} {expected}; se encontró {actual}.")
    versions[name] = actual

# Configuración sintética de comprobación. No carga aplicaciones de negocio ni auth.
settings.configure(
    SECRET_KEY="comprobacion-sintetica-sin-uso-en-el-producto",
    INSTALLED_APPS=["rest_framework"],
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
    USE_TZ=True,
    TIME_ZONE="America/Havana",
)
django.setup()
from django.core.checks import run_checks  # noqa: E402
from django.db import connection  # noqa: E402

errors = [error for error in run_checks() if error.is_serious()]
if errors:
    raise SystemExit("\n".join(str(error) for error in errors))
if connection.vendor != "postgresql" or connection.connection is not None:
    raise SystemExit("La comprobación debe cargar PostgreSQL sin abrir una conexión.")
if django.VERSION[:2] != (5, 2) or not rest_framework.VERSION.startswith("3.18."):
    raise SystemExit("Las series instaladas no corresponden a la arquitectura.")

print(
    json.dumps(
        {
            "python": platform.python_version(),
            "paquetes": versions,
            "adaptador_postgresql": psycopg.pq.__impl__,
            "libpq": psycopg.pq.version(),
            "comprobaciones_django": "Correctas con configuración sintética",
            "conexion_base": "No realizada",
            "migraciones": "No ejecutadas",
        },
        ensure_ascii=False,
        indent=2,
    )
)
