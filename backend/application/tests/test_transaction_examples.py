"""Contratos y límites del ejemplo, sin base de datos."""

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from application.examples.confirmation import (
    ConfirmationExampleReceipt,
    cancel_confirmation_example,
    prepare_confirmation_example,
)
from core.clock import FixedClock
from core.correlation import OperationContext
from modules.access.contracts import (
    AccessFacts,
    Action,
    ActorFacts,
    ContextFacts,
    ContextKind,
    ResourceFacts,
    ResourceKind,
)
from modules.access.policies import authorize
from modules.identity.selectors import lock_account_states, lock_confirmation
from modules.notifications.contracts import ConfirmationExampleIntent
from modules.notifications.selectors import lock_confirmation_outbox

NOW = datetime(2026, 11, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    "action", [Action.CONFIRMATION_SAMPLE_PREPARE, Action.CONFIRMATION_SAMPLE_CANCEL]
)
def test_sample_actions_require_own_account_and_personal_context(action):
    account_id, other = uuid4(), uuid4()
    values = dict(
        action=action,
        actor=ActorFacts(account_id, is_active=True),
        context=ContextFacts(ContextKind.PERSONAL),
        resource=ResourceFacts(ResourceKind.ACCOUNT, id=account_id, owner_account_id=account_id),
        facts=AccessFacts(),
        now=NOW,
    )
    assert authorize(**values)
    assert not authorize(
        **{
            **values,
            "resource": ResourceFacts(ResourceKind.ACCOUNT, id=other, owner_account_id=other),
        }
    )
    assert not authorize(**{**values, "context": ContextFacts(ContextKind.ORGANIZATION, other)})
    assert not authorize(
        **{
            **values,
            "resource": ResourceFacts(ResourceKind.ACCOUNT, id=other, owner_account_id=account_id),
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_account_id": "client"},
        {"account_id": None},
        {"operation": None},
        {"expires_at": datetime(2026, 1, 1)},
    ],
)
def test_bad_inputs_fail_before_accessing_database(changes):
    values = dict(
        actor_account_id=uuid4(),
        account_id=uuid4(),
        expires_at=NOW + timedelta(days=1),
        operation=OperationContext.start(clock=FixedClock(NOW)),
    )
    with pytest.raises((TypeError, ValueError)):
        prepare_confirmation_example(**{**values, **changes})


def test_invalid_challenge_reference_does_not_start_transaction():
    with pytest.raises(TypeError):
        cancel_confirmation_example(
            actor_account_id=uuid4(),
            account_id=uuid4(),
            challenge_id="client",
            operation=OperationContext.start(clock=FixedClock(NOW)),
        )


def test_receipt_and_intent_are_immutable_and_private_destination_is_not_repr():
    intent = ConfirmationExampleIntent(uuid4(), uuid4(), "private-synthetic@example.invalid")
    assert "private-synthetic" not in repr(intent)
    with pytest.raises(FrozenInstanceError):
        intent.destination = "other@example.invalid"
    receipt = ConfirmationExampleReceipt(uuid4(), uuid4(), (uuid4(),), uuid4())
    with pytest.raises(FrozenInstanceError):
        receipt.outbox_ids = ()
    with pytest.raises(TypeError):
        ConfirmationExampleIntent("client", uuid4(), "a@example.invalid")


@pytest.mark.parametrize(
    "call",
    [
        lambda: lock_account_states(account_ids=(uuid4(),)),
        lambda: lock_confirmation(account_id=uuid4(), challenge_id=uuid4()),
        lambda: lock_confirmation_outbox(challenge_id=uuid4()),
    ],
)
def test_lock_interfaces_require_transaction_before_database_access(call):
    with pytest.raises(RuntimeError):
        call()


def test_coordinator_uses_owner_interfaces_and_has_no_orm_or_external_effects():
    path = Path(__file__).resolve().parents[1] / "examples/confirmation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not node.module.endswith("models")
            assert node.module not in {"django.core.mail", "smtplib", "requests", "httpx"}
        if isinstance(node, ast.Attribute):
            assert node.attr not in {
                "objects",
                "cursor",
                "get_model",
                "on_commit",
                "commit",
                "rollback",
            }
    # Cada caso debe delimitar atomic; no se acredita la atomicidad por este análisis estático.
    public = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.endswith("confirmation_example")
    ]
    assert len(public) == 2
    assert all(
        any(isinstance(node, ast.With) for node in ast.walk(function)) for function in public
    )
