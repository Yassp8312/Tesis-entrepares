"""Flujo local reproducible de calidad; PostgreSQL solo mediante opción explícita."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def command_paths():
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise ValueError("Se requieren Node y npm en PATH.")
    candidates = (
        [Path(npm).resolve()]
        if os.name != "nt"
        else [
            Path(npm).parent / "node_modules/npm/bin/npm-cli.js",
            Path(node).parent / "node_modules/npm/bin/npm-cli.js",
        ]
    )
    npm_cli = next(
        (path for path in candidates if path.name == "npm-cli.js" and path.is_file()), None
    )
    uv = ROOT / ".tools/uv/0.13.6" / ("uv.exe" if os.name == "nt" else "uv")
    if not npm_cli or not uv.is_file():
        raise ValueError("Primero prepara el entorno y la distribución de npm.")
    return str(node), [str(node), str(npm_cli)], str(uv)


def isolated_environment():
    prefixes = (
        "DJANGO_",
        "POSTGRES_",
        "EMAIL_",
        "PYTEST_",
        "VITE_",
        "ENTREPARES_",
        "UV_",
        "NPM_CONFIG_",
    )
    result = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(prefixes)
        and key.upper() not in {"PYTHONPATH", "NODE_OPTIONS"}
    }
    result.update(
        PYTHONIOENCODING="utf-8",
        UV_PYTHON_INSTALL_DIR=str(ROOT / ".tools/python"),
        UV_CACHE_DIR=str(ROOT / ".tools/cache"),
        UV_NO_PROGRESS="1",
    )
    return result


def test_counts(path):
    report = ElementTree.parse(path).getroot()
    cases = list(report.iter("testcase"))
    if not cases:
        raise ValueError("El ejecutor no produjo casos de prueba.")
    return {
        "tests": len(cases),
        "failed": len(list(report.iter("failure"))) + len(list(report.iter("error"))),
        "skipped": len(list(report.iter("skipped"))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--postgresql",
        action="store_true",
        help="Añade integración en el cluster privado ya preparado.",
    )
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / ".cache/comprobaciones" / stamp
    output.mkdir(parents=True)
    environment = isolated_environment()
    report = {
        "started_utc": stamp,
        "postgresql_requested": args.postgresql,
        "steps": [],
        "completed": False,
        "locks": {
            name: sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ["uv.lock", "frontend/package-lock.json"]
        },
    }

    def save():
        (output / "informe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def run(name, command, cwd=ROOT):
        print(f"Comprobando {name}…", flush=True)
        started = time.monotonic()
        log = output / (name + ".log")
        with log.open("w", encoding="utf-8") as stream:
            try:
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(f"No se completó el comando: {type(error).__name__}.\n")
                code = -1
        report["steps"].append(
            {
                "name": name,
                "command": list(map(str, command)),
                "exit_code": code,
                "seconds": round(time.monotonic() - started, 3),
                "log": log.name,
            }
        )
        save()
        if code:
            raise ValueError(f"Falló {name}; consulta {log}.")

    try:
        node, npm, uv = command_paths()
        manifest = json.loads((ROOT / "frontend/package.json").read_text())
        for name, command, expected in [
            ("node", [node, "--version"], "v" + manifest["engines"]["node"]),
            ("npm", [*npm, "--version"], manifest["engines"]["npm"]),
            ("uv", [uv, "--version"], "uv 0.13.6"),
        ]:
            run("version-" + name, command)
            actual = (output / ("version-" + name + ".log")).read_text().strip()
            if (actual.split(" (", 1)[0] if name == "uv" else actual) != expected:
                raise ValueError(f"La versión instalada de {name} difiere de la fijada.")
        run("arquitectura", [sys.executable, "scripts/verificar_arquitectura.py"])
        run("bloqueo-python", [uv, "--offline", "lock", "--check"])
        run("compatibilidad-python", [uv, "--offline", "pip", "check", "--python", sys.executable])
        run("dependencias-python", [sys.executable, "scripts/verificar_dependencias.py"])
        run("analisis-python", [sys.executable, "-m", "ruff", "check", "backend", "scripts"])
        run(
            "formato-python",
            [sys.executable, "-m", "ruff", "format", "--check", "backend", "scripts"],
        )
        run(
            "pruebas-python",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--ds=config.settings.test",
                "-m",
                "not postgresql",
                "--junitxml=" + str(output / "python.xml"),
                "--basetemp=" + str(output / "pytest"),
            ],
        )
        run("dependencias-node", [*npm, "ls", "--all"], ROOT / "frontend")
        run("muestra-vue", [*npm, "run", "check:deps"], ROOT / "frontend")
        tests = [
            str(path.relative_to(ROOT / "frontend"))
            for path in sorted((ROOT / "frontend/tests").glob("*.test.ts"))
        ]
        run(
            "pruebas-vue",
            [
                node,
                "--test",
                "--test-reporter=junit",
                "--test-reporter-destination=" + str(output / "frontend.xml"),
                *tests,
            ],
            ROOT / "frontend",
        )
        run("tipos-y-build-vue", [*npm, "run", "build"], ROOT / "frontend")
        run("preparar-web", [sys.executable, "scripts/preparar_web.py"])
        for name, arguments in [
            ("django-check", ["check"]),
            ("collectstatic", ["collectstatic", "--noinput"]),
        ]:
            run(
                name,
                [
                    sys.executable,
                    "backend/manage.py",
                    *arguments,
                    "--settings=config.settings.checks",
                ],
            )
        report["tests"] = {
            "python": test_counts(output / "python.xml"),
            "frontend": test_counts(output / "frontend.xml"),
        }
        if args.postgresql:
            pwsh = shutil.which("pwsh")
            if not pwsh:
                raise ValueError("La integración local requiere PowerShell 7.")
            run(
                "integracion-postgresql",
                [
                    pwsh,
                    "-NoProfile",
                    "-File",
                    "scripts/probar.ps1",
                    "integracion",
                    "-q",
                    "--junitxml=" + (output / "postgresql.xml").relative_to(ROOT).as_posix(),
                ],
            )
            report["tests"]["postgresql"] = test_counts(output / "postgresql.xml")
            run(
                "migraciones",
                [
                    pwsh,
                    "-NoProfile",
                    "-File",
                    "scripts/django.ps1",
                    "makemigrations",
                    "--check",
                    "--dry-run",
                ],
            )
        if any(item["failed"] for item in report["tests"].values()):
            raise ValueError("Los informes registran casos fallidos.")
        report["completed"] = True
        print("Comprobaciones correctas.", flush=True)
        return 0
    except (ValueError, OSError, ElementTree.ParseError) as error:
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        save()
        print(f"Informe: {output / 'informe.json'}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
