"""SP02-T14: coordinación ejecutable de muestra, sin completar el flujo de identidad.

Orden: cuentas UUID ascendentes, comprobación y salidas UUID ascendentes.
Los escritores que cambien los hechos usados deben compartir esas anclas.
"""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from core.clock import as_utc
from core.correlation import OperationContext
from modules.access.contracts import (
    AccessDecision,
    AccessFacts,
    Action,
    ActorFacts,
    ContextFacts,
    ContextKind,
    ResourceFacts,
    ResourceKind,
    RestrictionContext,
    RestrictionFacts,
)
from modules.access.policies import authorize
from modules.audit import commands as audit_commands
from modules.audit.contracts import (
    ActorKind,
    AuditEntry,
    AuditProjection,
    AuditReason,
    AuditState,
)
from modules.audit.contracts import (
    ContextKind as AuditContextKind,
)
from modules.identity import commands as identity_commands
from modules.identity import selectors as identity_selectors
from modules.identity.contracts import ConfirmationConflict
from modules.moderation.selectors import get_account_restrictions
from modules.notifications import commands as notification_commands
from modules.notifications import selectors as notification_selectors
from modules.notifications.contracts import ConfirmationExampleIntent


@dataclass(frozen=True, slots=True)
class ConfirmationExampleReceipt:
    challenge_id: UUID
    audit_event_id: UUID
    outbox_ids: tuple[UUID, ...]
    correlation_id: UUID


class ExampleAccessDenied(Exception):
    def __init__(self, decision: AccessDecision):
        self.decision = decision
        super().__init__("La operación de muestra no está autorizada.")


def _inputs(actor_account_id, account_id, operation):
    if not isinstance(actor_account_id, UUID) or not isinstance(account_id, UUID):
        raise TypeError("Se requieren referencias de cuenta internas.")
    if not isinstance(operation, OperationContext):
        raise TypeError("Se requiere contexto de operación explícito.")


def _authorize_current(actor_account_id, account_id, operation, action):
    accounts = identity_selectors.lock_account_states(account_ids=(actor_account_id, account_id))
    actor_state = next((item for item in accounts if item.account_id == actor_account_id), None)
    actor = (
        ActorFacts(actor_state.account_id, is_active=actor_state.is_active)
        if actor_state
        else ActorFacts()
    )
    current = get_account_restrictions(account_id=actor_account_id)
    facts = AccessFacts(
        restrictions=tuple(
            RestrictionFacts(
                item.account_id,
                item.capability_code,
                RestrictionContext(item.context),
                item.starts_at,
                item.ends_at,
                item.revoked_at,
                item.is_ban,
            )
            for item in current
        )
    )
    # Leer el reloj después de esperar las anclas; nunca reutilizar una decisión previa.
    decision = authorize(
        action=action,
        actor=actor,
        context=ContextFacts(ContextKind.PERSONAL),
        resource=ResourceFacts(ResourceKind.ACCOUNT, id=account_id, owner_account_id=account_id),
        facts=facts,
        now=operation.now(),
    )
    if not decision:
        raise ExampleAccessDenied(decision)
    return next(item for item in accounts if item.account_id == account_id)


def prepare_confirmation_example(*, actor_account_id, account_id, expires_at, operation):
    """T02 + T37 + T35 en la misma atomic. Entrada interna; expires_at no es campo HTTP."""
    _inputs(actor_account_id, account_id, operation)
    expires_at = as_utc(expires_at)
    with transaction.atomic():
        account = _authorize_current(
            actor_account_id, account_id, operation, Action.CONFIRMATION_SAMPLE_PREPARE
        )
        challenge = identity_commands.create_confirmation_example(
            account_id=account_id,
            expires_at=expires_at,
            operation=operation,
        )
        audit = audit_commands.append_event(
            entry=AuditEntry(
                ActorKind.ACCOUNT,
                AuditContextKind.PERSONAL,
                Action.CONFIRMATION_SAMPLE_PREPARE.value,
                "identity.email_challenge",
                challenge.challenge_id,
                actor_account_id=actor_account_id,
                reason=AuditReason.CREATED,
                after_state=AuditProjection(status=AuditState.PENDING),
            ),
            operation=operation,
        )
        outbox = notification_commands.enqueue_confirmation_example(
            intent=ConfirmationExampleIntent(challenge.challenge_id, account_id, account.email),
            operation=operation,
        )
        return ConfirmationExampleReceipt(
            challenge.challenge_id, audit.event_id, (outbox.message_id,), operation.correlation_id
        )


def cancel_confirmation_example(*, actor_account_id, account_id, challenge_id, operation):
    """Revalida M08/M01, invalida T02, audita T37 y cancela T35 conjuntamente."""
    _inputs(actor_account_id, account_id, operation)
    if not isinstance(challenge_id, UUID):
        raise TypeError("Se requiere referencia de comprobación interna.")
    with transaction.atomic():
        _authorize_current(
            actor_account_id, account_id, operation, Action.CONFIRMATION_SAMPLE_CANCEL
        )
        challenge = identity_selectors.lock_confirmation(
            account_id=account_id, challenge_id=challenge_id
        )
        if challenge is None:
            raise ConfirmationConflict("La comprobación no admite la operación de muestra.")
        notification_selectors.lock_confirmation_outbox(challenge_id=challenge_id)
        # Una espera en cualquier bloqueo puede cruzar el inicio/fin de una medida.
        _authorize_current(
            actor_account_id, account_id, operation, Action.CONFIRMATION_SAMPLE_CANCEL
        )
        identity_commands.invalidate_confirmation_example(
            account_id=account_id,
            challenge_id=challenge_id,
            operation=operation,
        )
        audit = audit_commands.append_event(
            entry=AuditEntry(
                ActorKind.ACCOUNT,
                AuditContextKind.PERSONAL,
                Action.CONFIRMATION_SAMPLE_CANCEL.value,
                "identity.email_challenge",
                challenge_id,
                actor_account_id=actor_account_id,
                reason=AuditReason.CANCELLED,
                before_state=AuditProjection(status=AuditState.PENDING),
                after_state=AuditProjection(status=AuditState.CANCELLED),
            ),
            operation=operation,
        )
        outbox_ids = notification_commands.cancel_confirmation_example(
            challenge_id=challenge_id, operation=operation
        )
        return ConfirmationExampleReceipt(
            challenge_id, audit.event_id, outbox_ids, operation.correlation_id
        )
