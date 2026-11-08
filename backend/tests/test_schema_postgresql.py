"""Conformidad global y corpus T01–T37; nunca se insertan datos en desarrollo."""

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.contrib.auth.hashers import is_password_usable
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from psycopg import sql

from modules.academics.selectors import get_personal_verification
from modules.opportunities.selectors import get_opportunity_funding
from modules.organizations.selectors import get_organization_verification
from modules.profiles.selectors import get_profile_completeness
from tests.support.factories import SyntheticFactory
from tests.support.schema import (
    canonical_type,
    compare_structure,
    inspect_schema,
    load_reference,
    probe_predicate,
    schema_report,
)

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]


def test_runtime_models_and_migration_state_cover_all_345_reference_fields():
    reference = load_reference()
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    for registry in (apps, executor.loader.project_state().apps):
        models = {model._meta.db_table: model for model in registry.get_models()}
        total = 0
        for table in reference["tables"]:
            declared = {
                field.column: field for field in models[table["name"]]._meta.concrete_fields
            }
            assert set(declared) == {field["name"] for field in table["fields"]}
            for field in table["fields"]:
                model_field = declared[field["name"]]
                assert canonical_type(model_field.db_type(connection)) == field["type"]
                assert model_field.null == field["nullable"]
                assert model_field.primary_key == field["pk"]
                total += 1
        assert total == 345


def counts():
    with connection.cursor() as cursor:
        result = {}
        for table in load_reference()["tables"]:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table["name"])))
            result[table["id"]] = cursor.fetchone()[0]
    return result


def test_global_catalog_and_predicates_match_identified_design_without_reading_rows():
    with CaptureQueriesContext(connection) as captured:
        report = schema_report(connection)
    assert report["matched"], report
    assert report["counts"] == {
        "tables": 37,
        "fields": 345,
        "foreign_keys": 85,
        "checks": 143,
        "views": 4,
        "infrastructure_tables": 8,
        "primary_keys": 37,
        "composite_foreign_keys": 7,
        "unique_constraints": 19,
        "indexes": 153,
    }
    assert len(report["predicates"]) == 156
    assert sum(item["cases"] for item in report["predicates"]) == 8568
    assert all(item["mismatches"] == 0 for item in report["predicates"])
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in captured)
    assert sum(note["kind"] == "unique_index_as_constraint" for note in report["notes"]) == 3
    assert sum(note["kind"] == "django_auxiliary_index" for note in report["notes"]) == 1
    target = Path(__file__).resolve().parents[2] / ".cache/sprint02/t16-esquema-pruebas.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("method", ["manual", "institutional_email"])
def test_factory_inserts_every_field_and_table_with_valid_references_and_safe_states(method):
    factory = SyntheticFactory()
    graph = factory.build_graph(verification_method=method)
    assert len(graph.records) == 37 and sum(len(row) for row in graph.records.values()) == 345
    assert set(counts().values()) == {1}
    with connection.cursor() as cursor:
        for table in factory.reference["tables"]:
            pk = next(field["name"] for field in table["fields"] if field["pk"])
            names = [field["name"] for field in table["fields"]]
            cursor.execute(
                sql.SQL("SELECT {} FROM {} WHERE {}=%s").format(
                    sql.SQL(",").join(map(sql.Identifier, names)),
                    sql.Identifier(table["name"]),
                    sql.Identifier(pk),
                ),
                [graph.identifier(table["id"])],
            )
            restored = dict(zip(names, cursor.fetchone(), strict=True))
            for field in table["fields"]:
                value = restored[field["name"]]
                if field["type"] == "jsonb" and isinstance(value, str):
                    restored[field["name"]] = json.loads(value)
            assert restored == graph.row(table["id"])
    assert not is_password_usable(graph.row("T01")["password"])
    assert graph.row("T01")["is_staff"] is False and graph.row("T01")["is_superuser"] is False
    assert (
        graph.row("T35")["status"] == "cancelled" and graph.row("T34")["cancelled_at"] is not None
    )
    assert graph.row("T17")["revoked_at"] is not None and graph.row("T28")["revoked_at"] is not None
    assert graph.row("T33")["ended_at"] is not None and graph.row("T14")["ended_at"] is not None
    assert graph.row("T02")["key_version"] == "sample-only"
    assert graph.row("T06")["value"] != graph.row("T22")["value"]
    assert get_profile_completeness(profile_id=graph.identifier("T04")).is_complete is True
    assert get_personal_verification(account_id=graph.identifier("T01")).is_verified is False
    assert (
        get_organization_verification(organization_id=graph.identifier("T15")).is_verified is False
    )
    assert get_opportunity_funding(opportunity_id=graph.identifier("T18")).is_funded is True


def test_two_namespaces_do_not_share_unique_slots_or_primary_references():
    first, second = SyntheticFactory().build_graph(), SyntheticFactory().build_graph()
    assert set(counts().values()) == {2}
    assert all(first.identifier(key) != second.identifier(key) for key in first.records)
    assert first.row("T35")["challenge_id"] != second.row("T35")["challenge_id"]


def test_partial_graph_failure_rolls_back_all_owners_and_keeps_existing_corpus():
    SyntheticFactory().build_graph()
    before = counts()

    class FailingFactory(SyntheticFactory):
        def insert(self, table, values):
            super().insert(table, values)
            if table["id"] == "T21":
                raise RuntimeError("Fallo sintético después de financiación.")

    with pytest.raises(RuntimeError, match="sintético"):
        FailingFactory().build_graph()
    assert counts() == before


@pytest.mark.parametrize(
    "key,name", [("T06", "uq_t06_01"), ("T22", "uq_t22_01"), ("T34", "uq_t34_01")]
)
def test_translated_unique_objects_preserve_duplicate_and_null_semantics(key, name):
    factory = SyntheticFactory()
    graph = factory.build_graph()
    row = graph.row(key)
    row["id"] = uuid4()
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            factory.insert(next(t for t in factory.reference["tables"] if t["id"] == key), row)
    assert error.value.__cause__.diag.constraint_name == name
    if key == "T34":
        assert row["channel"] is None


def test_undocumented_adjustments_fail_even_if_shape_counts_match():
    reference = load_reference()
    observed = inspect_schema(connection, reference)
    report = compare_structure(
        reference, observed, {"unique_index_constraints": [], "auxiliary_indexes": []}
    )
    assert {
        ("T06", "unique_inventory"),
        ("T22", "unique_inventory"),
        ("T34", "unique_inventory"),
        ("T32", "index_inventory"),
    } <= {(item["location"], item["attribute"]) for item in report["differences"]}


@pytest.mark.parametrize(
    "change,attribute",
    [
        ("type", "type"),
        ("nullable", "nullable"),
        ("default", "default"),
        ("fk_delete", "fk_definition"),
        ("fk_order", "fk_definition"),
        ("deferred", "constraint_enforcement"),
        ("desc", "index_keys"),
        ("opclass", "operator_classes"),
        ("nulls", "index_uniqueness"),
        ("auxiliary", "auxiliary_index_definition"),
    ],
)
def test_structural_drift_is_not_accepted_by_counts_alone(change, attribute):
    reference = load_reference()
    observed = copy.deepcopy(inspect_schema(connection, reference))
    account = observed["tables"]["identity_account"]
    if change in ("type", "nullable", "default"):
        field = next(f for f in account["fields"] if f["name"] == "email")
        field.update(
            {"type": "varchar(100)"}
            if change == "type"
            else {"nullable": True}
            if change == "nullable"
            else {"default": "'changed'::character varying"}
        )
    if change == "fk_delete":
        observed["tables"]["identity_email_challenge"]["constraints"]["fk_t02_01"]["delete"] = "a"
    if change == "fk_order":
        observed["tables"]["access_grant"]["constraints"]["fk_t33_07"]["reference"].reverse()
    if change == "deferred":
        observed["tables"]["identity_email_challenge"]["constraints"]["fk_t02_01"]["deferrable"] = (
            True
        )
    if change == "desc":
        observed["tables"]["opportunities_opportunity"]["indexes"]["ix_t18_02"]["keys"][0] = (
            "published_at"
        )
    if change == "opclass":
        account["indexes"]["uq_t01_01"]["operator_classes"] = ["varchar_pattern_ops"]
    if change == "nulls":
        observed["tables"]["notifications_notice"]["indexes"]["uq_t34_01"]["nulls_not_distinct"] = (
            False
        )
    if change == "auxiliary":
        observed["tables"]["access_capability"]["indexes"]["access_capability_code_72401c64_like"][
            "unique"
        ] = True
    report = compare_structure(reference, observed)
    assert any(item["attribute"] == attribute for item in report["differences"])


class RevertTestSchema(Exception):
    pass


def test_same_named_check_weakened_to_true_is_detected_and_ddl_rolled_back():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    table = load_reference()["tables"][0]
    with pytest.raises(RevertTestSchema):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE identity_account DROP CONSTRAINT ck_t01_01")
                cursor.execute("ALTER TABLE identity_account ADD CONSTRAINT ck_t01_01 CHECK (true)")
            actual = inspect_schema(connection, load_reference())
            expression = actual["tables"]["identity_account"]["constraints"]["ck_t01_01"][
                "expression"
            ]
            result = probe_predicate(connection, table, table["checks"]["ck_t01_01"], expression)
            assert result["mismatches"] > 0
            raise RevertTestSchema()
    restored = inspect_schema(connection, load_reference())["tables"]["identity_account"][
        "constraints"
    ]["ck_t01_01"]["expression"]
    assert (
        probe_predicate(connection, table, table["checks"]["ck_t01_01"], restored)["mismatches"]
        == 0
    )


def test_changed_fk_action_and_deferability_are_detected_then_rolled_back():
    assert connection.settings_dict["NAME"] == "test_entrepares"
    reference = load_reference()
    with pytest.raises(RevertTestSchema):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE identity_email_challenge DROP CONSTRAINT fk_t02_01")
                cursor.execute(
                    "ALTER TABLE identity_email_challenge ADD CONSTRAINT fk_t02_01 FOREIGN KEY (account_id) REFERENCES identity_account(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED"
                )
            result = compare_structure(reference, inspect_schema(connection, reference))
            assert {r["attribute"] for r in result["differences"]} >= {
                "constraint_enforcement",
                "fk_definition",
            }
            raise RevertTestSchema()
    assert not compare_structure(reference, inspect_schema(connection, reference))["differences"]


def test_null_acceptance_and_partial_index_selection_remain_distinct():
    table = next(t for t in load_reference()["tables"] if t["id"] == "T04")
    # CHECK acepta UNKNOWN; un filtro de índice solo selecciona TRUE.
    assert (
        probe_predicate(
            connection,
            table,
            "experience_years >= 0",
            "experience_years IS NULL OR experience_years >= 0",
        )["mismatches"]
        == 0
    )
    assert (
        probe_predicate(
            connection,
            table,
            "experience_years >= 0",
            "experience_years IS NULL OR experience_years >= 0",
            check=False,
        )["mismatches"]
        > 0
    )
