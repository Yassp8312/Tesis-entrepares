"""Privacidad de la entrada M10 sin permitir acceso a una base."""

from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from core.clock import FixedClock
from core.correlation import OperationContext
from modules.audit.commands import append_event
from modules.audit.contracts import (
    ActorKind,
    AuditEntry,
    AuditProjection,
    AuditReason,
    AuditState,
    ContextKind,
)


def entry_values():
    return {
        "actor_kind": ActorKind.SYSTEM,
        "context_kind": ContextKind.SYSTEM,
        "action_code": "synthetic.record.created",
        "resource_kind": "synthetic.record",
        "resource_id": uuid4(),
    }


def test_closed_projection_returns_fresh_minimum_data():
    related = uuid4()
    projection = AuditProjection(
        status=AuditState.APPROVED, related_resource_id=related, revision=3
    )
    expected = {"status": "approved", "related_resource_id": str(related), "revision": 3}
    assert projection.to_dict() == expected
    exported = projection.to_dict()
    exported["status"] = "cambiado-fuera-del-contrato"
    assert projection.to_dict() == expected
    assert AuditProjection().to_dict() == {}
    with pytest.raises(FrozenInstanceError):
        projection.revision = 4


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "approved"},
        {"status": {"password": "clave-sintetica-no-real"}},
        {"related_resource_id": "correo-sintetico@example.org"},
        {"revision": -1},
        {"revision": True},
        {"revision": 1.5},
        {"revision": "3"},
        {"revision": 2_147_483_648},
    ],
)
def test_projection_rejects_free_text_nested_objects_and_invalid_revisions(changes):
    with pytest.raises((TypeError, ValueError)):
        AuditProjection(**changes)


@pytest.mark.parametrize("key", ["password", "token", "document", "email", "contacts"])
def test_projection_has_no_channel_for_unlisted_sensitive_fields(key):
    with pytest.raises(TypeError) as error:
        AuditProjection(**{key: "contenido-sintetico-privado"})
    assert "contenido-sintetico-privado" not in str(error.value)


@pytest.mark.parametrize(
    "code",
    [
        "",
        " ",
        "a" * 81,
        "usuario@example.org",
        "https://example.org/?token=synthetic",
        "acción con relato",
        "synthetic\nrecord",
    ],
)
@pytest.mark.parametrize("field", ["action_code", "resource_kind"])
def test_technical_identifiers_reject_payload_text(field, code):
    with pytest.raises(ValueError):
        AuditEntry(**{**entry_values(), field: code})


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_kind": "system"},
        {"context_kind": "system"},
        {"resource_id": "not-a-uuid"},
        {"actor_account_id": "not-a-uuid"},
        {"organization_id": "not-a-uuid"},
        {"academic_scope_id": "not-a-uuid"},
        {"actor_account_id": uuid4()},
        {"context_kind": ContextKind.PERSONAL},
        {"actor_kind": ActorKind.ACCOUNT, "context_kind": ContextKind.PERSONAL},
        {"actor_kind": ActorKind.ACCOUNT, "actor_account_id": uuid4()},
        {
            "actor_kind": ActorKind.ACCOUNT,
            "actor_account_id": uuid4(),
            "context_kind": ContextKind.ORGANIZATION,
        },
        {"organization_id": uuid4()},
    ],
)
def test_entry_rejects_incoherent_actors_contexts_and_reference_types(changes):
    with pytest.raises((TypeError, ValueError)):
        AuditEntry(**{**entry_values(), **changes})


@pytest.mark.parametrize(
    "field,payload",
    [
        ("reason", "clave-sintetica-no-real"),
        ("reason", "https://example.org/?token=firma-sintetica"),
        ("reason", {"document": "documento-sintetico-completo"}),
        ("before_state", {"password": "clave-sintetica-no-real"}),
        ("after_state", {"nested": {"contacts": ["privado@example.org"]}}),
        ("after_state", {"status": "approved"}),
    ],
)
def test_entry_rejects_raw_reasons_and_arbitrary_snapshots(field, payload):
    with pytest.raises(TypeError) as error:
        AuditEntry(**{**entry_values(), field: payload})
    assert "clave-sintetica" not in str(error.value)
    assert "firma-sintetica" not in str(error.value)
    assert "documento-sintetico" not in str(error.value)
    assert "privado@example.org" not in str(error.value)


def test_entry_is_immutable_and_technical_reason_is_explicit():
    entry = AuditEntry(
        **entry_values(),
        reason=AuditReason.CREATED,
        after_state=AuditProjection(status=AuditState.PENDING),
    )
    assert entry.reason.value == "record_created"
    assert "synthetic.record.created" not in repr(entry)
    with pytest.raises(FrozenInstanceError):
        entry.reason = AuditReason.UPDATED


def test_writer_revalidates_entry_before_any_database_access():
    from datetime import UTC, datetime

    operation = OperationContext.start(clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)))
    entry = AuditEntry(**entry_values())
    object.__setattr__(entry, "after_state", {"password": "clave-sintetica-no-real"})
    with pytest.raises(TypeError):
        append_event(entry=entry, operation=operation)
    with pytest.raises(TypeError):
        append_event(entry={"password": "clave-sintetica-no-real"}, operation=operation)
    with pytest.raises(TypeError):
        append_event(entry=AuditEntry(**entry_values()), operation=None)


def test_projection_is_revalidated_if_its_frozen_state_was_bypassed():
    projection = AuditProjection(status=AuditState.PENDING)
    object.__setattr__(projection, "status", "token-sintetico")
    with pytest.raises(TypeError):
        projection.to_dict()
    with pytest.raises(TypeError):
        replace(AuditEntry(**entry_values()), after_state=projection)
