"""Contraste de catálogo y predicados sobre valores sintéticos; no lee filas reales."""

import itertools
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from psycopg import sql

REFERENCE = Path(__file__).resolve().parents[1] / "reference/logical-schema.json"
ADJUSTMENTS = Path(__file__).resolve().parents[1] / "reference/schema-adjustments.json"
INFRASTRUCTURE = frozenset(
    {
        "auth_group",
        "auth_group_permissions",
        "auth_permission",
        "django_content_type",
        "django_migrations",
        "django_session",
        "identity_account_groups",
        "identity_account_user_permissions",
    }
)
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


def load_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def load_adjustments():
    return json.loads(ADJUSTMENTS.read_text(encoding="utf-8"))


def compact(text):
    return "".join(
        part if part.startswith("'") else re.sub(r"\s+", "", part).lower()
        for part in re.split(r"('(?:''|[^'])*')", text)
    )


def canonical_type(kind):
    kind = (
        kind.replace("character varying", "varchar")
        .replace("timestamp with time zone", "timestamptz")
        .replace("time without time zone", "time")
    )
    kind = re.sub(r",\s+", ",", kind)
    if not re.fullmatch(
        r"uuid|varchar\(\d+\)|numeric\(\d+,\d+\)|text|boolean|integer|jsonb|timestamptz|date|time",
        kind,
    ):
        raise ValueError("Tipo fuera del contrato de referencia.")
    return kind


def canonical_default(expression):
    if expression is None:
        return None
    # Cast de constante a su tipo de columna ya comprobado: no elimina operaciones.
    expression = re.sub(
        r"::(?:character varying(?:\(\d+\))?|text|jsonb|numeric(?:\(\d+,\d+\))?)$",
        "",
        expression.strip(),
    )
    return compact(expression)


def split_keys(expression):
    depth, start, result = 0, 0, []
    for i, char in enumerate(expression):
        depth += (char == "(") - (char == ")")
        if char == "," and not depth:
            result.append(expression[start:i].strip())
            start = i + 1
    result.append(expression[start:].strip())
    return result


def canonical_key(expression):
    normalized = re.sub(r"::text\b", "", expression.lower()).replace('"', "").strip()
    if re.fullmatch(r"lower\(\(*\s*[a-z_]+\s*\)*\)", normalized):
        return re.sub(r"[\s()]", "", normalized)
    normalized = re.sub(r"\s+asc$", "", normalized)
    if re.fullmatch(r"[a-z_]+(?:\s+desc)?", normalized):
        return " ".join(normalized.split())
    raise ValueError("Expresión de índice fuera del subconjunto declarado.")


def inspect_schema(connection, reference):
    names = [table["name"] for table in reference["tables"]]
    result = {"tables": {}, "views": {}, "infrastructure": [], "unexpected": []}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relkind IN ('r','p','v') ORDER BY c.relname"
        )
        for name, kind in cursor:
            if name in names and kind == "r":
                result["tables"][name] = {"fields": [], "constraints": {}, "indexes": {}}
            elif name in reference["views"] and kind == "v":
                result["views"][name] = {}
            elif name in INFRASTRUCTURE and kind == "r":
                result["infrastructure"].append(name)
            else:
                result["unexpected"].append(name)
        cursor.execute(
            """SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull,pg_get_expr(d.adbin,d.adrelid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname=current_schema() AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""",
            [names + list(reference["views"])],
        )
        for table, name, kind, nullable, default in cursor:
            if table in result["tables"]:
                result["tables"][table]["fields"].append(
                    {"name": name, "type": kind, "nullable": nullable, "default": default}
                )
            elif table in result["views"]:
                result["views"][table][name] = kind
        cursor.execute(
            """SELECT c.relname,k.conname,k.contype,k.convalidated,k.condeferrable,k.condeferred,
            ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY s(num,ord) JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=s.num ORDER BY s.ord),
            target.relname,tn.nspname,
            ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY s(num,ord) JOIN pg_attribute a ON a.attrelid=k.confrelid AND a.attnum=s.num ORDER BY s.ord),
            k.confdeltype,k.confupdtype,k.confmatchtype,pg_get_expr(k.conbin,k.conrelid)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_class target ON target.oid=k.confrelid LEFT JOIN pg_namespace tn ON tn.oid=target.relnamespace
            WHERE n.nspname=current_schema() AND c.relname=ANY(%s) ORDER BY c.relname,k.conname""",
            [names],
        )
        for row in cursor:
            (
                table,
                name,
                kind,
                validated,
                deferrable,
                deferred,
                fields,
                target,
                schema,
                refs,
                delete,
                update,
                match,
                expression,
            ) = row
            result["tables"][table]["constraints"][name] = {
                "kind": kind,
                "validated": validated,
                "deferrable": deferrable,
                "deferred": deferred,
                "fields": fields,
                "target": target,
                "target_schema": schema,
                "reference": refs,
                "delete": delete,
                "update": update,
                "match": match,
                "expression": expression,
            }
        cursor.execute(
            """SELECT c.relname,ix.relname,i.indisunique,i.indisprimary,i.indnullsnotdistinct,i.indisvalid,i.indisready,i.indimmediate,am.amname,
            ARRAY(SELECT pg_get_indexdef(i.indexrelid,s.num,true) FROM generate_series(1,i.indnkeyatts) s(num) ORDER BY s.num),
            pg_get_expr(i.indpred,i.indrelid),i.indnatts-i.indnkeyatts,i.indoption::int2[],
            ARRAY(SELECT o.opcname FROM unnest(i.indclass::oid[]) WITH ORDINALITY k(id,ord) JOIN pg_opclass o ON o.oid=k.id ORDER BY k.ord)
            FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_class ix ON ix.oid=i.indexrelid JOIN pg_am am ON am.oid=ix.relam
            WHERE n.nspname=current_schema() AND c.relname=ANY(%s) ORDER BY c.relname,ix.relname""",
            [names],
        )
        for (
            table,
            name,
            unique,
            primary,
            nulls,
            valid,
            ready,
            immediate,
            method,
            keys,
            predicate,
            included,
            options,
            operator_classes,
        ) in cursor:
            keys = [
                key + (" DESC" if option & 1 else "")
                for key, option in zip(keys, options, strict=False)
            ]
            result["tables"][table]["indexes"][name] = {
                "unique": unique,
                "primary": primary,
                "nulls_not_distinct": nulls,
                "valid": valid,
                "ready": ready,
                "immediate": immediate,
                "method": method,
                "keys": keys,
                "where": predicate,
                "included": included,
                "default_null_order": all(
                    bool(option & 1) == bool(option & 2) for option in options
                ),
                "operator_classes": operator_classes,
            }
        cursor.execute("SELECT current_schema()")
        result["schema"] = cursor.fetchone()[0]
    return result


def compare_structure(reference, actual, adjustments=None):
    adjustments = load_adjustments() if adjustments is None else adjustments
    differences, notes = [], []

    def check(ok, location, attribute):
        if not ok:
            differences.append({"location": location, "attribute": attribute})

    check(not actual["unexpected"], "schema", "unexpected_relations")
    check(set(actual["infrastructure"]) == INFRASTRUCTURE, "schema", "infrastructure_inventory")
    for table in reference["tables"]:
        name, label = table["name"], table["id"]
        check(name in actual["tables"], label, "table")
        if name not in actual["tables"]:
            continue
        observed = actual["tables"][name]
        by_name = {field["name"]: field for field in observed["fields"]}
        check(set(by_name) == {f["name"] for f in table["fields"]}, label, "field_inventory")
        if [f["name"] for f in table["fields"]] != [f["name"] for f in observed["fields"]]:
            notes.append(
                {
                    "table": label,
                    "kind": "physical_column_order",
                    "reason": "Herencia/creación ORM; comparación por nombre, no por posición física",
                }
            )
        for field in table["fields"]:
            current = by_name.get(field["name"])
            if current is None:
                continue
            check(
                canonical_type(current["type"]) == field["type"],
                label + "." + field["name"],
                "type",
            )
            check(current["nullable"] == field["nullable"], label + "." + field["name"], "nullable")
            check(
                canonical_default(current["default"]) == canonical_default(field["default"]),
                label + "." + field["name"],
                "default",
            )
        constraints = observed["constraints"]
        primary = [c["fields"] for c in constraints.values() if c["kind"] == "p"]
        check(primary == [[f["name"] for f in table["fields"] if f["pk"]]], label, "primary_key")
        check(
            {k for k, v in constraints.items() if v["kind"] == "c"} == set(table["checks"]),
            label,
            "check_inventory",
        )
        translated = {
            item["name"]
            for item in adjustments["unique_index_constraints"]
            if item["table"] == name
        }
        translated_specs = {
            index["name"]: split_keys(index["expression"])
            for index in table["indexes"]
            if index["name"] in translated and index["unique"] and index["where"] is None
        }
        check(set(translated_specs) == translated, label, "declared_unique_translation")
        check(
            {k: v["fields"] for k, v in constraints.items() if v["kind"] == "u"}
            == table["unique"] | translated_specs,
            label,
            "unique_inventory",
        )
        for item in adjustments["unique_index_constraints"]:
            if item["table"] == name:
                notes.append(
                    {
                        "table": label,
                        "kind": "unique_index_as_constraint",
                        "name": item["name"],
                        "reason": item["reason"],
                    }
                )
        check(
            {k for k, v in constraints.items() if v["kind"] == "f"}
            == {fk["name"] for fk in table["foreign_keys"]},
            label,
            "fk_inventory",
        )
        for constraint_name, constraint in constraints.items():
            check(
                constraint["validated"]
                and not constraint["deferrable"]
                and not constraint["deferred"],
                constraint_name,
                "constraint_enforcement",
            )
        for foreign in table["foreign_keys"]:
            current = constraints.get(foreign["name"])
            if current:
                expected = (
                    foreign["fields"],
                    foreign["target"],
                    actual["schema"],
                    foreign["reference"],
                    "r",
                    "a",
                    "s",
                )
                received = tuple(
                    current[k]
                    for k in (
                        "fields",
                        "target",
                        "target_schema",
                        "reference",
                        "delete",
                        "update",
                        "match",
                    )
                )
                check(received == expected, foreign["name"], "fk_definition")
        auxiliary = [item for item in adjustments["auxiliary_indexes"] if item["table"] == name]
        expected_indexes = (
            {index["name"] for index in table["indexes"]}
            | {k for k, v in constraints.items() if v["kind"] in ("p", "u")}
            | {item["name"] for item in auxiliary}
        )
        check(set(observed["indexes"]) == expected_indexes, label, "index_inventory")
        for item in auxiliary:
            current = observed["indexes"].get(item["name"])
            check(
                current is not None
                and current["keys"] == item["keys"]
                and current["operator_classes"] == item["operator_classes"]
                and current["unique"] == item["unique"]
                and current["where"] is None
                and not current["nulls_not_distinct"],
                item["name"],
                "auxiliary_index_definition",
            )
            notes.append(
                {
                    "table": label,
                    "kind": "django_auxiliary_index",
                    "name": item["name"],
                    "reason": item["reason"],
                }
            )
        for index in table["indexes"]:
            current = observed["indexes"].get(index["name"])
            if current is None:
                continue
            check(
                current["unique"] == index["unique"]
                and current["nulls_not_distinct"] == index["nulls_not_distinct"],
                index["name"],
                "index_uniqueness",
            )
            check(
                [canonical_key(k) for k in current["keys"]]
                == [canonical_key(k) for k in split_keys(index["expression"])],
                index["name"],
                "index_keys",
            )
            check(
                (current["where"] is None) == (index["where"] is None),
                index["name"],
                "index_predicate_presence",
            )
        for index_name, index in observed["indexes"].items():
            check(
                index["valid"]
                and index["ready"]
                and index["immediate"]
                and index["method"] == "btree"
                and index["included"] == 0
                and index["default_null_order"],
                index_name,
                "index_enforcement",
            )
            if index_name not in {item["name"] for item in auxiliary}:
                opclasses = []
                for key in index["keys"]:
                    canonical = canonical_key(key)
                    field_kind = (
                        "text"
                        if canonical.startswith("lower")
                        else canonical_type(by_name[canonical.split()[0]]["type"])
                    )
                    opclasses.append(
                        "text_ops"
                        if field_kind.startswith("varchar") or field_kind == "text"
                        else "numeric_ops"
                        if field_kind.startswith("numeric")
                        else {
                            "uuid": "uuid_ops",
                            "integer": "int4_ops",
                            "boolean": "bool_ops",
                            "timestamptz": "timestamptz_ops",
                            "date": "date_ops",
                            "time": "time_ops",
                            "jsonb": "jsonb_ops",
                        }[field_kind]
                    )
                check(index["operator_classes"] == opclasses, index_name, "operator_classes")
            constraint = constraints.get(index_name)
            if constraint and constraint["kind"] in ("p", "u"):
                check(
                    index["unique"]
                    and index["primary"] == (constraint["kind"] == "p")
                    and index["where"] is None,
                    index_name,
                    "constraint_index",
                )
                if index_name not in translated:
                    check(not index["nulls_not_distinct"], index_name, "constraint_nulls_distinct")
    check(actual["views"] == reference["views"], "schema", "derived_view_columns")
    return {"differences": differences, "notes": notes}


def safe_expression(expression, fields):
    outside = re.sub(r"'(?:''|[^'])*'", "", expression)
    functions = set(
        "length btrim trim lower jsonb_typeof in any not and or numeric varchar varying".split()
    )
    calls = {name.lower() for name in re.findall(r"([a-zA-Z_][a-zA-Z_0-9]*)\s*\(", outside)}
    if not calls <= functions:
        raise ValueError("La expresión contiene llamadas no admitidas.")
    allowed = set(fields) | set(
        "length btrim trim lower jsonb_typeof both from and or not in is null true false any array text character varying integer numeric boolean jsonb uuid date time timestamp timestamptz with without zone".split()
    )
    if (
        ";" in outside
        or "--" in outside
        or "/*" in outside
        or "." in re.sub(r"\d+\.\d+", "0", outside)
    ):
        raise ValueError("Expresión fuera del subconjunto SELECT de prueba.")
    if not {token.lower() for token in re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", outside)} <= allowed:
        raise ValueError("La expresión contiene identificadores no admitidos.")


def _values(field, literals):
    kind = field["type"]
    if kind.startswith("varchar") or kind == "text":
        maximum = int(re.search(r"\d+", kind)[0]) if kind.startswith("varchar") else 500
        values = list(
            dict.fromkeys(
                value[:maximum]
                for value in [
                    "",
                    " ",
                    "\t",
                    "SINTETICO",
                    "ABC",
                    "abc",
                    "AB",
                    "123",
                    " example.invalid ",
                    *literals,
                ]
            )
        )
    elif kind == "uuid":
        values = [UUID(int=1), UUID(int=2)]
    elif kind == "integer":
        values = [-1, 0, 1, 2]
    elif kind.startswith("numeric"):
        values = [Decimal("-1"), Decimal("0"), Decimal("0.1"), Decimal("1")]
    elif kind == "boolean":
        values = [False, True]
    elif kind == "timestamptz":
        values = [NOW - timedelta(seconds=1), NOW, NOW + timedelta(seconds=1)]
    elif kind == "date":
        values = [date(2026, 11, 7), date(2026, 11, 8)]
    elif kind == "time":
        values = [time(0), time(12)]
    elif kind == "jsonb":
        values = ["{}", '{"synthetic":1}', "[]", "null", "true", '"synthetic"']
    else:
        raise ValueError("Tipo de frontera no soportado.")
    return ([None] if field["nullable"] else []) + values


def probe_predicate(connection, table, reference_expression, actual_expression, *, check=True):
    fields = {field["name"]: field for field in table["fields"]}
    safe_expression(reference_expression, fields)
    safe_expression(actual_expression, fields)
    outside = re.sub(r"'(?:''|[^'])*'", "", reference_expression + " " + actual_expression)
    used = [name for name in fields if re.search(r"\b" + re.escape(name) + r"\b", outside)]
    literals = [
        value.replace("''", "'")
        for value in re.findall(r"'((?:''|[^'])*)'", reference_expression + " " + actual_expression)
    ]
    candidates = (
        itertools.product(*(_values(fields[name], literals) for name in used))
        if used
        else iter([()])
    )
    suffix = "IS NOT FALSE" if check else "IS TRUE"
    compare = sql.SQL("(({}) {}) IS DISTINCT FROM (({}) {})").format(
        sql.SQL(reference_expression), sql.SQL(suffix), sql.SQL(actual_expression), sql.SQL(suffix)
    )
    tested = mismatches = 0
    with connection.cursor() as cursor:
        while batch := list(itertools.islice(candidates, 250)):
            if used:
                row = sql.SQL("({})").format(
                    sql.SQL(",").join(
                        sql.SQL("%s::" + canonical_type(fields[name]["type"])) for name in used
                    )
                )
                query = sql.SQL(
                    "SELECT count(*) FROM (VALUES {}) AS candidate({}) WHERE {}"
                ).format(
                    sql.SQL(",").join([row] * len(batch)),
                    sql.SQL(",").join(map(sql.Identifier, used)),
                    compare,
                )
                parameters = [value for values in batch for value in values]
            else:
                query, parameters = (
                    sql.SQL("SELECT CASE WHEN {} THEN 1 ELSE 0 END").format(compare),
                    [],
                )
            cursor.execute(query, parameters)
            mismatches += cursor.fetchone()[0]
            tested += len(batch)
    return {"cases": tested, "mismatches": mismatches}


def compare_predicates(connection, reference, actual):
    results = []
    for table in reference["tables"]:
        observed = actual["tables"].get(table["name"])
        if not observed:
            continue
        for name, expression in table["checks"].items():
            constraint = observed["constraints"].get(name)
            if constraint and constraint["kind"] == "c":
                results.append(
                    {
                        "table": table["id"],
                        "name": name,
                        "kind": "check",
                        **probe_predicate(connection, table, expression, constraint["expression"]),
                    }
                )
        for index in table["indexes"]:
            current = observed["indexes"].get(index["name"])
            if index["where"] and current and current["where"]:
                results.append(
                    {
                        "table": table["id"],
                        "name": index["name"],
                        "kind": "index_predicate",
                        **probe_predicate(
                            connection, table, index["where"], current["where"], check=False
                        ),
                    }
                )
    return results


def schema_report(connection):
    reference = load_reference()
    actual = inspect_schema(connection, reference)
    comparison = compare_structure(reference, actual)
    predicates = compare_predicates(connection, reference, actual)
    return {
        "reference": {
            "dictionary_sha256": reference["dictionary_sha256"],
            "sql_sha256": reference["sql_sha256"],
        },
        "counts": {
            "tables": len(actual["tables"]),
            "fields": sum(len(t["fields"]) for t in actual["tables"].values()),
            "foreign_keys": sum(
                c["kind"] == "f"
                for t in actual["tables"].values()
                for c in t["constraints"].values()
            ),
            "checks": sum(
                c["kind"] == "c"
                for t in actual["tables"].values()
                for c in t["constraints"].values()
            ),
            "views": len(actual["views"]),
            "infrastructure_tables": len(actual["infrastructure"]),
            "primary_keys": sum(
                c["kind"] == "p"
                for t in actual["tables"].values()
                for c in t["constraints"].values()
            ),
            "composite_foreign_keys": sum(
                c["kind"] == "f" and len(c["fields"]) > 1
                for t in actual["tables"].values()
                for c in t["constraints"].values()
            ),
            "unique_constraints": sum(
                c["kind"] == "u"
                for t in actual["tables"].values()
                for c in t["constraints"].values()
            ),
            "indexes": sum(len(t["indexes"]) for t in actual["tables"].values()),
        },
        **comparison,
        "predicates": predicates,
        "matched": not comparison["differences"]
        and all(item["mismatches"] == 0 for item in predicates),
        "limit": "Equivalencia de aceptación en el conjunto finito explícito de fronteras; no prueba formal universal ni validación de procesos funcionales",
    }
