"""Control inicial AT01; no demuestra propiedad de cada SQL ni imports dinámicos."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from config.architecture import forbidden_imports, scan_backend

BACKEND = Path(__file__).resolve().parents[1]


def test_current_core_and_business_packages_respect_boundaries():
    examined, violations = scan_backend(BACKEND)
    assert examined > 0
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
        ("import backend.application.cases", "modules.profiles.commands", True),
        ("from application import cases", "modules.identity.management.commands", True),
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
        ("from application import cases", "api.v1.views", False),
    ],
)
def test_guard_allows_owner_dependencies_and_authorized_cli(source, module, is_package):
    assert forbidden_imports(source, module, is_package) == []


@pytest.mark.parametrize(
    "module,source,expected",
    [
        ("modules/profiles/commands/bad.py", "from application import cases", 1),
        ("modules/profiles/selectors/bad.py", "from django.http import HttpRequest", 1),
        ("modules/identity/management/commands/example.py", "from application import cases", 0),
        ("core/bad.py", "def broken(:", 1),
    ],
)
def test_architecture_cli_returns_failure_for_real_source_files(tmp_path, module, source, expected):
    (tmp_path / "core").mkdir()
    (tmp_path / "modules").mkdir()
    file = tmp_path / module
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND.parent / "scripts/verificar_arquitectura.py"),
            "--backend",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == expected, result.stderr
    report = json.loads(result.stdout)
    assert report["examined"] == 1
    assert bool(report["violations"]) == bool(expected)
    if expected:
        assert report["violations"][0]["file"] == module
        assert report["violations"][0]["line"] == 1
