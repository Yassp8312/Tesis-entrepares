"""Grafo sintético identificado de T01–T37, solo para la base efímera de pruebas.

Prueba persistencia y referencias; no representa decisiones institucionales ni
ejecuta transiciones de aplicación. No se instala en desarrollo o producción.
"""

import copy
import os
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4, uuid5

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
from psycopg import sql
from psycopg.types.json import Jsonb

from core.clock import as_utc
from tests.support.schema import NOW, load_reference

ORDER = (
    "T01 T02 T03 T08 T09 T10 T11 T04 T05 T06 T07 T12 T13 T14 T15 T16 T17 T18 T19 T20 T21 T22 T23 T24 T32 T33 T25 T26 T27 T28 T29 T30 T31 T34 T35 T36 T37"
).split()


@dataclass(frozen=True, slots=True)
class SyntheticGraph:
    namespace: UUID
    records: Mapping[str, Mapping[str, object]]

    def row(self, table_id):
        return copy.deepcopy(dict(self.records[table_id]))

    def identifier(self, table_id):
        row = self.records[table_id]
        return row.get("id", row.get("opportunity_id", row.get("publication_id", row.get("code"))))


class SyntheticFactory:
    def __init__(self, *, namespace=None, now=NOW):
        self.namespace = uuid4() if namespace is None else namespace
        if not isinstance(self.namespace, UUID):
            raise TypeError("El conjunto sintético requiere un namespace UUID.")
        self.now = as_utc(now)
        self.reference = load_reference()
        self._guarded_connection = None

    def uuid(self, label):
        return uuid5(self.namespace, label)

    @property
    def email(self):
        return f"synthetic-{self.namespace.hex}@example.invalid"

    def _guard(self):
        if (
            connection.vendor != "postgresql"
            or settings.SETTINGS_MODULE != "config.settings.test"
            or connection.settings_dict["NAME"] != "test_entrepares"
            or connection.settings_dict["USER"] != "entrepares_test"
            or connection.settings_dict["HOST"] != "127.0.0.1"
        ):
            raise RuntimeError(
                "Las fábricas solo insertan en la base efímera identificada de pruebas."
            )
        if (
            self._guarded_connection is None
            or self._guarded_connection is not connection.connection
        ):
            expected = os.environ.get("POSTGRES_TEST_CLUSTER_NAME", "")
            if not expected.startswith("entrepares-local-"):
                raise RuntimeError("La fábrica requiere el identificador del cluster privado.")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('cluster_name'),current_setting('server_version_num'),current_database(),current_user"
                )
                cluster, version, database, role = cursor.fetchone()
            if (
                cluster != expected
                or not 170000 <= int(version) < 180000
                or (database, role) != ("test_entrepares", "entrepares_test")
            ):
                raise RuntimeError(
                    "El destino de las fábricas no es el cluster de pruebas identificado."
                )
            self._guarded_connection = connection.connection

    def _base_value(self, table_id, field):
        name, kind, default = field["name"], field["type"], field["default"]
        if field["nullable"]:
            return None
        if default == "gen_random_uuid()":
            return self.uuid(table_id + "." + name)
        if default == "CURRENT_TIMESTAMP":
            return self.now
        if default in ("true", "false"):
            return default == "true"
        if default and default.startswith("'"):
            value = default.split("'", 2)[1]
            return {} if kind == "jsonb" else value
        if default is not None:
            return int(default)
        if kind == "uuid":
            return self.uuid(table_id + "." + name)
        if kind == "integer":
            return 1
        if kind.startswith("numeric"):
            return Decimal("0")
        if kind == "boolean":
            return False
        if kind == "timestamptz":
            return self.now
        if kind == "date":
            return self.now.date() + timedelta(days=1)
        if kind == "time":
            return self.now.time().replace(tzinfo=None)
        if kind == "jsonb":
            return {}
        return f"SINTETICO {table_id}.{name} {self.namespace.hex}"

    def build_graph(self, *, verification_method="manual") -> SyntheticGraph:
        self._guard()
        if verification_method not in ("manual", "institutional_email"):
            raise ValueError("Variante de prueba no identificada.")
        tables = {table["id"]: table for table in self.reference["tables"]}
        by_name = {table["name"]: table["id"] for table in tables.values()}
        records = {}

        def identifier(key):
            table, row = tables[key], records[key]
            return row[next(field["name"] for field in table["fields"] if field["pk"])]

        with transaction.atomic():
            for key in ORDER:
                table = tables[key]
                fields = {field["name"]: field for field in table["fields"]}
                values = {name: self._base_value(key, field) for name, field in fields.items()}
                for foreign in table["foreign_keys"]:
                    if all(not fields[name]["nullable"] for name in foreign["fields"]):
                        parent = records[by_name[foreign["target"]]]
                        values.update(
                            zip(
                                foreign["fields"],
                                (parent[name] for name in foreign["reference"]),
                                strict=True,
                            )
                        )
                actor = identifier("T01") if "T01" in records else None
                one_day_ago = self.now - timedelta(days=1)
                overrides = {
                    "T01": {"email": self.email, "password": make_password(None)},
                    "T02": {
                        "purpose": "email_confirmation",
                        "email_snapshot": self.email,
                        "key_version": "sample-only",
                        "expires_at": self.now + timedelta(days=1),
                    },
                    "T03": {"claimed_email": self.email},
                    "T05": {"condition": "student"},
                    "T06": {
                        "kind": "email",
                        "value": f"profile-{self.namespace.hex}@example.invalid",
                    },
                    "T08": {"kind": "university", "origin": "declared"},
                    "T09": {"kind": "institution"},
                    "T10": {"origin": "declared"},
                    "T11": {"domain_ascii": f"synthetic-{self.namespace.hex}.example.invalid"},
                    "T12": {"method": verification_method},
                    "T14": {"ended_at": self.now, "ended_by": actor},
                    "T15": {"kind": "private"},
                    "T17": {"created_at": one_day_ago, "revoked_at": self.now, "revoked_by": actor},
                    "T18": {
                        "owner_account_id": actor,
                        "lifecycle": "active",
                        "visibility": "hidden",
                        "validity_revision": 1,
                        "created_at": one_day_ago,
                        "published_at": one_day_ago,
                        "expires_at": self.now + timedelta(days=1),
                    },
                    "T19": {
                        "event_kind": "publish",
                        "actor_id": actor,
                        "from_state": "draft",
                        "to_state": "active",
                        "new_expires_at": self.now + timedelta(days=1),
                        "created_at": one_day_ago,
                    },
                    "T21": {
                        "currency_code": "CUP",
                        "coverage": "project",
                        "payment_kind": "one_off",
                    },
                    "T22": {
                        "kind": "email",
                        "value": f"public-{self.namespace.hex}@example.invalid",
                    },
                    "T23": {"kind": "event", "owner_account_id": actor},
                    "T24": {
                        "mode": "online",
                        "participation_url": f"https://event.example.invalid/{self.namespace.hex}",
                    },
                    "T25": {
                        "starts_at": one_day_ago,
                        "ends_at": self.now,
                        "revoked_at": self.now,
                        "revoked_by": actor,
                    },
                    "T27": {
                        "outcome": "violation",
                        "content_action": "none",
                        "created_at": one_day_ago,
                    },
                    "T28": {
                        "kind": "ban",
                        "starts_at": one_day_ago,
                        "ends_at": self.now,
                        "revoked_at": self.now,
                        "revoked_by": actor,
                    },
                    "T29": {"context_kind": "personal"},
                    "T31": {"outcome": "revoked"},
                    "T32": {"code": f"synthetic.schema.{self.namespace.hex}"},
                    "T33": {
                        "scope_kind": "global",
                        "source": "bootstrap",
                        "valid_from": one_day_ago,
                        "valid_until": self.now,
                        "ended_at": self.now,
                        "ended_by": actor,
                        "end_reason": "SINTETICO autorización terminada",
                    },
                    "T34": {
                        "scheduled_for": self.now,
                        "cancelled_at": self.now,
                        "cancellation_reason": "SINTETICO aviso cancelado",
                    },
                    "T35": {
                        "recipient_account_id": actor,
                        "channel": "email",
                        "destination": self.email,
                        "template_key": "transaction_sample.email_confirmation",
                        "idempotency_key": f"synthetic.schema.{self.namespace.hex}",
                        "status": "cancelled",
                        "available_at": self.now + timedelta(days=365),
                    },
                    "T36": {
                        "result": "unknown",
                        "finished_at": self.now,
                        "error_code": "synthetic.not_delivered",
                    },
                    "T37": {
                        "actor_kind": "system",
                        "context_kind": "system",
                        "action_code": "synthetic.schema.created",
                        "resource_kind": "synthetic.dataset",
                        "resource_id": self.uuid("dataset"),
                        "correlation_id": self.uuid("correlation"),
                    },
                }
                values.update(overrides.get(key, {}))
                if key == "T12":
                    values.update(
                        {"academic_scope_id": identifier("T09")}
                        if verification_method == "manual"
                        else {"challenge_id": identifier("T02"), "domain_id": identifier("T11")}
                    )
                if key == "T25":
                    values.update(
                        opportunity_id=identifier("T18"), source_grant_id=identifier("T33")
                    )
                if key == "T26":
                    values.update(publication_id=identifier("T23"), created_at=one_day_ago)
                if key == "T35":
                    values.update(
                        challenge_id=identifier("T02"),
                        payload={"challenge_id": str(identifier("T02"))},
                    )
                self.insert(table, values)
                records[key] = MappingProxyType(values)
        return SyntheticGraph(self.namespace, MappingProxyType(records))

    def insert(self, table, values):
        self._guard()
        known = {item["id"]: item for item in self.reference["tables"]}
        if table != known.get(table.get("id")) or set(values) != {
            field["name"] for field in table["fields"]
        }:
            raise ValueError("La fábrica solo escribe columnas del contrato identificado.")
        json_fields = {field["name"] for field in table["fields"] if field["type"] == "jsonb"}
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table["name"]),
                    sql.SQL(",").join(map(sql.Identifier, values)),
                    sql.SQL(",").join(sql.Placeholder() for _ in values),
                ),
                [
                    Jsonb(value) if key in json_fields and value is not None else value
                    for key, value in values.items()
                ],
            )
