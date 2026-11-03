"""Control inicial AT01; no demuestra propiedad de cada SQL ni imports dinámicos."""

import ast
import json
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
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


def imports_in(source, module, is_package):
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            yield base
            yield from (base + "." + alias.name for alias in node.names if alias.name != "*")


def forbidden_imports(source, module, is_package=False):
    parts = module.split(".")
    is_core = parts[0] == "core"
    is_business = parts[0] == "modules" and len(parts) >= 2
    is_cli = parts[2:4] == ["management", "commands"]
    rejected = []
    for target in imports_in(source, module, is_package):
        if is_core:
            if target.split(".")[0] not in sys.stdlib_module_names | {"core"}:
                rejected.append(target)
        elif is_business:
            if any(target == name or target.startswith(name + ".") for name in HTTP):
                rejected.append(target)
            elif (target == "application" or target.startswith("application.")) and not is_cli:
                rejected.append(target)
            else:
                imported = target.split(".")
                if (
                    len(imported) >= 3
                    and imported[0] == "modules"
                    and imported[1] != parts[1]
                    and imported[2] == "models"
                ):
                    rejected.append(target)
    return rejected


def test_current_core_and_business_packages_respect_boundaries():
    violations = []
    for root in [BACKEND / "core", BACKEND / "modules"]:
        for path in root.rglob("*.py"):
            relative = path.relative_to(BACKEND)
            if "tests" in relative.parts:
                continue
            is_package = path.name == "__init__.py"
            parts = relative.with_suffix("").parts
            module = ".".join(parts[:-1] if is_package else parts)
            rejected = forbidden_imports(path.read_text(encoding="utf-8"), module, is_package)
            violations.extend(f"{relative}: {target}" for target in rejected)
    assert violations == []


def test_all_ten_owners_have_explicit_interface_packages():
    registry = json.loads(
        (BACKEND.parent / "docs/base-documental.json").read_text(encoding="utf-8")
    )
    assert len(registry["modulos"]) == 10
    for module in registry["modulos"]:
        for interface in ["commands", "selectors", "contracts"]:
            assert (BACKEND.parent / module["ubicacion"] / interface / "__init__.py").is_file()


@pytest.mark.parametrize(
    "source,module,is_package",
    [
        ("import application.cases", "modules.profiles.commands", True),
        ("from application import cases", "modules.profiles.selectors", True),
        ("from django.http import HttpRequest", "modules.profiles.contracts", True),
        ("from django import http", "modules.profiles.commands", True),
        ("from rest_framework import serializers", "modules.profiles.contracts", True),
        ("import api.v1", "modules.profiles.models", False),
        ("from modules.organizations import models", "modules.profiles.selectors", True),
        ("from ...organizations.models import Organization", "modules.profiles.commands", True),
        ("from modules.identity.models import Account", "core.clock", False),
        ("from django.utils import timezone", "core.clock", False),
    ],
)
def test_guard_rejects_injected_violations(source, module, is_package):
    assert forbidden_imports(source, module, is_package)


@pytest.mark.parametrize(
    "source,module,is_package",
    [
        ("from .contracts import AccountState", "modules.identity.commands", False),
        ("from ..contracts import AccountState", "modules.identity.commands", True),
        ("from datetime import UTC, datetime", "core.clock", False),
        ("from core.clock import Clock", "modules.opportunities.commands", True),
        ("from django.db import models", "modules.profiles.models", False),
        ("from application import cases", "modules.notifications.management.commands.send", False),
    ],
)
def test_guard_allows_owner_dependencies_and_authorized_cli(source, module, is_package):
    assert forbidden_imports(source, module, is_package) == []
