"""Extrae contrato de prueba del diseño fijado; no conecta a BD ni copia documentos."""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_SHA256 = "2ae98fdeb8f6fdf0efeac37b7d9b93d10750ae86fb3d43528c1b40f4d466c585"


def compact(text):
    # Conserva exactamente los literales; solo normaliza el SQL exterior.
    return "".join(
        part if part.startswith("'") else re.sub(r"\s+", "", part).lower()
        for part in re.split(r"('(?:''|[^'])*')", text)
    )


def split_items(text):
    result, start, depth, quoted, index = [], 0, 0, False, 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted:
            depth += (char == "(") - (char == ")")
            if char == "," and depth == 0:
                result.append(text[start:index].strip())
                start = index + 1
            if depth < 0:
                raise ValueError("SQL de referencia no balanceado.")
        index += 1
    if quoted or depth:
        raise ValueError("SQL de referencia no balanceado.")
    result.append(text[start:].strip())
    return result


def extract(dictionary_path, sql_path):
    registry = json.loads((ROOT / "docs/base-documental.json").read_text(encoding="utf-8"))
    dictionary_bytes, sql_bytes = dictionary_path.read_bytes(), sql_path.read_bytes()
    if hashlib.sha256(dictionary_bytes).hexdigest() != registry["fuentes"][1]["sha256"]:
        raise ValueError("El diccionario no corresponde al diseño identificado.")
    if hashlib.sha256(sql_bytes).hexdigest() != SQL_SHA256:
        raise ValueError("El SQL no corresponde a la revisión de referencia.")
    source = json.loads(dictionary_bytes)
    ddl = sql_bytes.decode("utf-8")
    definitions = dict(re.findall(r"CREATE TABLE ([a-z_]+) \((.*?)\n\);", ddl, re.S))
    tables = []
    for table in source["tables"]:
        actual_fields, checks, unique = {}, {}, {}
        for part in split_items(definitions[table["name"]]):
            if part.startswith("CONSTRAINT "):
                match = re.fullmatch(r"CONSTRAINT (\w+) CHECK \((.*)\)", part, re.S)
                if match:
                    checks[match[1]] = match[2]
                    continue
                match = re.fullmatch(r"CONSTRAINT (\w+) UNIQUE \((.*)\)", part, re.S)
                if match:
                    unique[match[1]] = [name.strip() for name in split_items(match[2])]
                    continue
                raise ValueError("Forma de restricción no identificada en el SQL.")
            match = re.fullmatch(
                r"(\w+) (uuid|varchar\(\d+\)|numeric\(\d+,\d+\)|text|boolean|integer|jsonb|timestamptz|date|time)(.*)",
                part,
                re.S,
            )
            if not match:
                raise ValueError("Tipo de campo no identificado en el SQL.")
            name, kind, suffix = match.groups()
            default = re.search(r"\bDEFAULT (.*?)(?: PRIMARY KEY)?$", suffix)
            actual_fields[name] = {
                "name": name,
                "type": kind,
                "nullable": "NOT NULL" not in suffix and "PRIMARY KEY" not in suffix,
                "default": default[1] if default else None,
                "pk": "PRIMARY KEY" in suffix,
            }
        fields = [
            {key: field[key] for key in ("name", "type", "nullable", "default", "pk")}
            for field in table["fields"]
        ]
        if actual_fields != {field["name"]: field for field in fields}:
            raise ValueError(f"Diccionario y SQL difieren en campos de {table['id']}.")
        expected_checks = {
            f"ck_{table['id'].lower()}_{i:02}": expression
            for i, expression in enumerate(table["checks"], 1)
        }
        if {k: compact(v) for k, v in checks.items()} != {
            k: compact(v) for k, v in expected_checks.items()
        }:
            raise ValueError(f"Diccionario y SQL difieren en CHECK de {table['id']}.")
        expected_unique = {
            f"uq_{table['id'].lower()}_key{i:02}": names
            for i, names in enumerate(table["unique"], 1)
        }
        if unique != expected_unique:
            raise ValueError(f"Diccionario y SQL difieren en claves de {table['id']}.")
        for fk in table["foreign_keys"]:
            statement = f"ALTER TABLE {table['name']} ADD CONSTRAINT {fk['name']} FOREIGN KEY ({', '.join(fk['fields'])}) REFERENCES {fk['target']} ({', '.join(fk['reference'])}) ON DELETE RESTRICT;"
            if compact(statement) not in compact(ddl):
                raise ValueError(f"FK no identificada en el SQL: {fk['name']}.")
        for index in table["indexes"]:
            statement = f"CREATE {'UNIQUE ' if index['unique'] else ''}INDEX {index['name']} ON {table['name']} ({index['expression']})"
            if index["nulls_not_distinct"]:
                statement += " NULLS NOT DISTINCT"
            if index["where"]:
                statement += " WHERE " + index["where"]
            if compact(statement + ";") not in compact(ddl):
                raise ValueError(f"Índice no identificado en el SQL: {index['name']}.")
        tables.append(
            {
                "id": table["id"],
                "name": table["name"],
                "module": table["module"],
                "fields": fields,
                "checks": expected_checks,
                "unique": expected_unique,
                "foreign_keys": table["foreign_keys"],
                "indexes": table["indexes"],
            }
        )
    if len(definitions) != len(tables) or ddl.count(" FOREIGN KEY (") != 85:
        raise ValueError("El inventario SQL de tablas/FK no coincide.")
    return {
        "version": source["version"],
        "dictionary_sha256": hashlib.sha256(dictionary_bytes).hexdigest(),
        "sql_sha256": SQL_SHA256,
        "scope": "Contrato estructural sin datos de participantes; no es un volcado ni una migración",
        "tables": tables,
        "views": {
            "model_profile_completeness": {
                "profile_id": "uuid",
                "account_id": "uuid",
                "is_complete": "boolean",
            },
            "model_personal_verification": {"account_id": "uuid", "is_verified": "boolean"},
            "model_organization_verification": {
                "organization_id": "uuid",
                "is_verified": "boolean",
            },
            "model_opportunity_funding": {"opportunity_id": "uuid", "is_funded": "boolean"},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--sql", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.dictionary, args.sql)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "tables": len(result["tables"]),
                "fields": sum(len(t["fields"]) for t in result["tables"]),
            }
        )
    )


if __name__ == "__main__":
    main()
