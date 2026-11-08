"""Contrato de referencia, normalización limitada y barreras de datos sintéticos."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from scripts.crear_referencia_esquema import compact, extract, split_items

from tests.support.factories import SyntheticFactory
from tests.support.schema import (
    canonical_default,
    canonical_key,
    canonical_type,
    load_adjustments,
    load_reference,
    safe_expression,
)


def test_reference_is_small_structural_projection_of_identified_sources():
    reference = load_reference()
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "docs/base-documental.json").read_text(encoding="utf-8"))
    assert reference["dictionary_sha256"] == registry["fuentes"][1]["sha256"]
    assert (
        reference["sql_sha256"]
        == "2ae98fdeb8f6fdf0efeac37b7d9b93d10750ae86fb3d43528c1b40f4d466c585"
    )
    assert len(reference["tables"]) == 37
    assert sum(len(table["fields"]) for table in reference["tables"]) == 345
    assert sum(len(table["foreign_keys"]) for table in reference["tables"]) == 85
    assert sum(len(table["checks"]) for table in reference["tables"]) == 143
    assert {table["module"] for table in reference["tables"]} == {f"M{i:02}" for i in range(1, 11)}
    assert set(reference["tables"][0]) == {
        "id",
        "name",
        "module",
        "fields",
        "checks",
        "unique",
        "foreign_keys",
        "indexes",
    }


def test_projection_is_reproducible_and_source_inputs_are_not_silently_accepted(tmp_path):
    path = tmp_path / "not-the-design.json"
    path.write_text('{"tables":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="diccionario"):
        extract(path, path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() != load_reference()["dictionary_sha256"]


def test_parser_preserves_literals_commas_and_parenthesized_numeric_types():
    assert split_items("a numeric(5,1), CONSTRAINT ck CHECK (b IN ('a,b', 'c''d'))") == [
        "a numeric(5,1)",
        "CONSTRAINT ck CHECK (b IN ('a,b', 'c''d'))",
    ]
    assert compact("LOWER ('ABC')") == compact("lower('ABC')")
    assert compact("'ABC'") != compact("'abc'")
    assert compact("'a b'") != compact("'ab'")


@pytest.mark.parametrize("text", ["a numeric(5,1", "a text)", "a 'unclosed"])
def test_parser_rejects_unbalanced_sql(text):
    with pytest.raises(ValueError):
        split_items(text)


@pytest.mark.parametrize(
    "actual,expected",
    [
        ("character varying(24)", "varchar(24)"),
        ("timestamp with time zone", "timestamptz"),
        ("time without time zone", "time"),
        ("numeric(18,2)", "numeric(18,2)"),
        ("numeric(5, 1)", "numeric(5,1)"),
    ],
)
def test_type_aliases_are_explicit(actual, expected):
    assert canonical_type(actual) == expected


def test_default_and_index_normalization_does_not_erase_meaning():
    assert canonical_default("'America/Havana'::character varying") == canonical_default(
        "'America/Havana'"
    )
    assert canonical_default("'a b'") != canonical_default("'ab'")
    assert canonical_default(None) is None
    assert canonical_key("lower((email)::text)") == canonical_key("lower(email)")
    assert canonical_key("published_at DESC") != canonical_key("published_at")
    with pytest.raises(ValueError):
        canonical_key("a + b")
    with pytest.raises(ValueError):
        canonical_type("text); DROP TABLE any_table")


@pytest.mark.parametrize(
    "expression",
    [
        "pg_sleep(1)=1",
        "email IS NOT NULL; DELETE FROM identity_account",
        "email IS NULL -- comment",
        "other_table.email IS NULL",
        "email IS NULL /* comment */",
        "exists(SELECT 1)",
        "email(1) IS NULL",
    ],
)
def test_predicate_evaluator_rejects_sql_outside_closed_subset(expression):
    with pytest.raises(ValueError):
        safe_expression(expression, {"email"})


def test_predicate_guard_allows_declared_json_and_whitespace_checks():
    safe_expression("jsonb_typeof(payload) = 'object'", {"payload"})
    safe_expression("length(TRIM(BOTH FROM email)) > 0", {"email"})


def test_adjustments_are_named_and_small_not_pattern_exemptions():
    adjustments = load_adjustments()
    assert {(a["table"], a["name"]) for a in adjustments["unique_index_constraints"]} == {
        ("profiles_contact", "uq_t06_01"),
        ("opportunities_contact", "uq_t22_01"),
        ("notifications_notice", "uq_t34_01"),
    }
    assert len(adjustments["auxiliary_indexes"]) == 1
    assert adjustments["auxiliary_indexes"][0]["name"] == "access_capability_code_72401c64_like"


def test_factory_namespace_is_deterministic_private_and_cannot_seed_development():
    one, two = SyntheticFactory(namespace=UUID(int=1)), SyntheticFactory(namespace=UUID(int=1))
    assert one.uuid("T01") == two.uuid("T01")
    assert one.email.endswith("@example.invalid")
    with pytest.raises(TypeError):
        SyntheticFactory(namespace="client")
    # Sin db fixture no existe destino efímero: falla antes de cualquier consulta/escritura.
    with pytest.raises(RuntimeError, match="efímera"):
        one.build_graph()
