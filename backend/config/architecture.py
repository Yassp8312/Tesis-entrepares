"""Análisis estático de dependencias; no ejecuta el código examinado."""

import ast
import sys
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path

HTTP = (
    "api",
    "rest_framework",
    "django.http",
    "django.views",
    "django.shortcuts",
    "django.urls",
    "http",
    "urllib.request",
    "requests",
    "httpx",
)


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    target: str
    rule: str


def imports_in(source, module, is_package):
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            yield base, node.lineno
            for alias in node.names:
                if alias.name != "*":
                    yield base + "." + alias.name, node.lineno


def boundary_rule(target, module, is_package):
    parts = module.split(".")
    target = target.removeprefix("backend.")
    imported = target.split(".")
    if parts[0] == "core":
        if imported[0] not in sys.stdlib_module_names | {"core"}:
            return "ARCH01: core solo depende de biblioteca estándar y core"
    elif parts[0] == "modules" and len(parts) >= 2:
        cli = len(parts) == 5 and parts[2:4] == ["management", "commands"] and not is_package
        if any(target == name or target.startswith(name + ".") for name in HTTP):
            return "ARCH02: negocio no importa HTTP"
        if imported[0] == "application" and not cli:
            return "ARCH03: negocio no importa application fuera de una entrada CLI"
        if (
            len(imported) >= 3
            and imported[0] == "modules"
            and imported[1] != parts[1]
            and imported[2] == "models"
        ):
            return "ARCH04: un propietario no importa modelos ajenos"
    return None


def forbidden_imports(source, module, is_package=False):
    return [
        target
        for target, _ in imports_in(source, module, is_package)
        if boundary_rule(target, module, is_package)
    ]


def scan_backend(backend: Path):
    if not all((backend / name).is_dir() for name in ["core", "modules"]):
        raise ValueError("Se requiere un backend con core y modules.")
    violations = []
    examined = 0
    for root in [backend / "core", backend / "modules"]:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(backend)
            if "tests" in relative.parts:
                continue
            examined += 1
            is_package = path.name == "__init__.py"
            parts = relative.with_suffix("").parts
            module = ".".join(parts[:-1] if is_package else parts)
            try:
                for target, line in imports_in(
                    path.read_text(encoding="utf-8"), module, is_package
                ):
                    rule = boundary_rule(target, module, is_package)
                    if rule:
                        violations.append(Violation(relative.as_posix(), line, target, rule))
            except (SyntaxError, ImportError, UnicodeError) as error:
                violations.append(
                    Violation(
                        relative.as_posix(),
                        getattr(error, "lineno", 1),
                        "",
                        "ARCH05: sintaxis o importación relativa no válida",
                    )
                )
    if not examined:
        raise ValueError("No hay archivos Python que examinar.")
    return examined, violations
