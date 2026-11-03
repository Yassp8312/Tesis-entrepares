"""Cluster privado de desarrollo y pruebas; no interviene servicios de Windows."""

import argparse
import json
import secrets
import shlex
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

from descargar_postgresql import ensure_runtime

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "scripts/postgresql-runtime.json"


def save_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def native(bin_dir, root, program, *arguments, check=True):
    # En Windows el proceso servidor puede heredar tuberías de pg_ctl y mantenerlas
    # abiertas después de que este termine. Un archivo evita esperar su EOF.
    with (root / "operaciones.log").open("ab") as log:
        result = subprocess.run(
            [str(bin_dir / program), *map(str, arguments)],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=90,
        )
    if check and result.returncode:
        raise RuntimeError(f"Falló {program}; consulta el registro privado operaciones.log.")
    return result


def paths():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    root = REPO / ".tools" / "postgresql" / spec["version"]
    return spec, root, root / "pgsql/bin", root / "data"


def read_state(root):
    path = root / "cluster.json"
    if not path.exists():
        raise RuntimeError("Primero ejecuta postgresql_local.py preparar.")
    return json.loads(path.read_text(encoding="utf-8"))


def administrator(root, state, database="postgres"):
    credentials = json.loads((root / "secrets.json").read_text(encoding="utf-8"))
    connection = psycopg.connect(
        host="127.0.0.1",
        port=state["port"],
        user="entrepares_bootstrap",
        password=credentials["admin"],
        dbname=database,
        connect_timeout=5,
        autocommit=True,
    )
    try:
        directory, version, cluster = connection.execute(
            "SELECT current_setting('data_directory'), current_setting('server_version'), "
            "current_setting('cluster_name')"
        ).fetchone()
        if (
            Path(directory).resolve() != (root / "data").resolve()
            or cluster != state["cluster_name"]
        ):
            raise RuntimeError(
                "El servidor conectado no corresponde al cluster privado del proyecto."
            )
        if version.split()[0] != state["version"]:
            raise RuntimeError("La versión conectada no coincide con el entorno fijado.")
    except Exception:
        connection.close()
        raise
    return connection


def start(root, bin_dir, data, state):
    result = native(bin_dir, root, "pg_ctl.exe", "status", "-D", data, check=False)
    if result.returncode != 0:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", state["port"]))
            except OSError as error:
                raise RuntimeError(
                    "El puerto está ocupado; no se interviene el proceso ajeno."
                ) from error
        native(
            bin_dir,
            root,
            "pg_ctl.exe",
            "start",
            "-D",
            data,
            "-l",
            root / "servidor.log",
            "-w",
            "-t",
            "30",
        )
    with administrator(root, state):
        pass


def configure_databases(root, state):
    credentials = json.loads((root / "secrets.json").read_text(encoding="utf-8"))
    with administrator(root, state) as connection:
        for role, key, createdb in [
            ("entrepares_dev", "development", False),
            ("entrepares_test", "test", True),
        ]:
            exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", [role]
            ).fetchone()
            verb = "ALTER" if exists else "CREATE"
            connection.execute(
                sql.SQL(
                    verb
                    + " ROLE {} LOGIN NOSUPERUSER {} NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.Identifier(role),
                    sql.SQL("CREATEDB" if createdb else "NOCREATEDB"),
                    sql.Literal(credentials[key]),
                )
            )
        for name, owner in [
            ("entrepares_development", "entrepares_dev"),
            ("entrepares_test", "entrepares_test"),
        ]:
            row = connection.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", [name]
            ).fetchone()
            if row and row[0] != owner:
                raise RuntimeError(
                    "Una base existente no tiene el propietario esperado; se conserva."
                )
            if not row:
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                        sql.Identifier(name), sql.Identifier(owner)
                    )
                )
            connection.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
            )
        for name in ["postgres", "template1"]:
            connection.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
            )
        connection.execute("GRANT CONNECT ON DATABASE postgres TO entrepares_test")
    for name, owner in [
        ("entrepares_development", "entrepares_dev"),
        ("entrepares_test", "entrepares_test"),
    ]:
        with administrator(root, state, name) as connection:
            connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.execute(
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(owner))
            )


def update_environment(root, state):
    path = REPO / ".env"
    if not path.exists():
        raise RuntimeError("Primero ejecuta scripts/preparar-configuracion.ps1.")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    existing = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip().startswith("POSTGRES_"):
            parsed = shlex.split(value, comments=False)
            existing[key.strip()] = parsed[0] if parsed else ""
    credentials = json.loads((root / "secrets.json").read_text(encoding="utf-8"))
    if existing.get("POSTGRES_PASSWORD") not in (None, "", credentials["development"]):
        raise RuntimeError(
            "La configuración existente contiene credenciales ajenas; no se sobrescriben."
        )
    if existing.get("POSTGRES_HOST", "127.0.0.1") != "127.0.0.1" or existing.get(
        "POSTGRES_USER", "entrepares"
    ) not in {"entrepares", "entrepares_dev"}:
        raise RuntimeError("La configuración existente apunta a otro destino; se conserva.")
    if existing.get("POSTGRES_DB", "entrepares_development") != "entrepares_development" or (
        existing.get("POSTGRES_PORT", "5432") not in {"5432", str(state["port"])}
    ):
        raise RuntimeError("La base o el puerto configurados son ajenos; se conservan.")
    values = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": str(state["port"]),
        "POSTGRES_DB": "entrepares_development",
        "POSTGRES_USER": "entrepares_dev",
        "POSTGRES_PASSWORD": credentials["development"],
        "POSTGRES_TEST_DB": "entrepares_test",
        "POSTGRES_TEST_USER": "entrepares_test",
        "POSTGRES_TEST_PASSWORD": credentials["test"],
        "POSTGRES_TEST_DB_NAME": "test_entrepares",
        "POSTGRES_TEST_CLUSTER_NAME": state["cluster_name"],
    }
    remaining = [line for line in lines if line.partition("=")[0].strip() not in values]
    remaining.extend(f"{key}='{value}'" for key, value in values.items())
    path.write_bytes(("\n".join(remaining) + "\n").encode("utf-8"))


def prepare(port):
    spec, root, bin_dir = ensure_runtime()
    data = root / "data"
    if (root / "cluster.json").exists():
        state = read_state(root)
        if port is not None and port != state["port"]:
            raise RuntimeError(
                "Un cluster existente conserva su puerto; no se reconfigura automáticamente."
            )
    else:
        if data.exists() and any(data.iterdir()):
            raise RuntimeError("El directorio de datos no está vacío; no se reinicializa.")
        state = {
            "version": spec["version"],
            "port": port or 55432,
            "cluster_name": "entrepares-local-" + uuid.uuid4().hex,
        }
        save_json(root / "cluster.json", state)
        save_json(
            root / "secrets.json",
            {key: secrets.token_urlsafe(32) for key in ["admin", "development", "test"]},
        )
    if not (data / "PG_VERSION").exists():
        credentials = json.loads((root / "secrets.json").read_text(encoding="utf-8"))
        password_file = root / "init-password.tmp"
        password_file.write_bytes((credentials["admin"] + "\n").encode("utf-8"))
        try:
            native(
                bin_dir,
                root,
                "initdb.exe",
                "-D",
                data,
                "-U",
                "entrepares_bootstrap",
                "--auth=scram-sha-256",
                "--pwfile",
                password_file,
                "--encoding=UTF8",
                "--locale=C",
                "--locale-provider=icu",
                "--icu-locale=und",
            )
        finally:
            password_file.unlink(missing_ok=True)
    # Se puede reanudar la preparación si se interrumpe después de initdb.
    configuration = data / "postgresql.conf"
    include = "include = 'entrepares-local.conf'"
    if include not in configuration.read_text(encoding="utf-8"):
        with configuration.open("a", encoding="utf-8") as output:
            output.write("\n# Entorno privado de Entrepares\n" + include + "\n")
    (data / "entrepares-local.conf").write_bytes(
        (
            "listen_addresses='127.0.0.1'\n"
            f"port={state['port']}\ncluster_name='{state['cluster_name']}'\n"
            "password_encryption='scram-sha-256'\nlog_min_error_statement='panic'\n"
            "max_connections=30\nshared_buffers='64MB'\ntimezone='UTC'\n"
        ).encode("utf-8")
    )
    (data / "pg_hba.conf").write_bytes(b"host all all 127.0.0.1/32 scram-sha-256\n")
    start(root, bin_dir, data, state)
    configure_databases(root, state)
    update_environment(root, state)
    print(
        f"PostgreSQL {state['version']} preparado en 127.0.0.1:{state['port']}; bases y usuarios separados."
    )


def main():
    if sys.platform != "win32":
        raise RuntimeError("Este aprovisionamiento usa la distribución Windows x64 documentada.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["preparar", "iniciar", "detener", "estado"])
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.accion == "preparar":
        if args.port is not None and not 1024 <= args.port <= 65535:
            raise RuntimeError("El puerto local debe estar entre 1024 y 65535.")
        prepare(args.port)
        return
    _, root, bin_dir, data = paths()
    state = read_state(root)
    if args.accion == "iniciar":
        start(root, bin_dir, data, state)
        print("Cluster privado iniciado y destino comprobado.")
    elif args.accion == "detener":
        if native(bin_dir, root, "pg_ctl.exe", "status", "-D", data, check=False).returncode == 0:
            with administrator(root, state):
                pass
            native(bin_dir, root, "pg_ctl.exe", "stop", "-D", data, "-m", "fast", "-w", "-t", "30")
        print("Cluster privado detenido.")
    else:
        running = (
            native(bin_dir, root, "pg_ctl.exe", "status", "-D", data, check=False).returncode == 0
        )
        if running:
            with administrator(root, state):
                pass
        print(json.dumps({"version": state["version"], "port": state["port"], "activo": running}))


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as error:
        raise SystemExit(
            f"Falló la operación PostgreSQL ({type(error).__name__}, SQLSTATE {error.sqlstate}); no se muestran credenciales."
        ) from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
