"""Escrituras propietarias de M10; application coordina los casos y transacciones."""

from core.correlation import OperationContext
from modules.audit.contracts import AuditEntry, AuditReceipt
from modules.audit.models import AuditEvent


def append_event(*, entry: AuditEntry, operation: OperationContext) -> AuditReceipt:
    """Añade una evidencia mínima en la transacción del llamador, sin efectos externos.

    El coordinador valida la autoridad y reúne la evidencia privada en sus propietarios.
    Esta interfaz no permite editar o borrar eventos ni serializar estados arbitrarios.
    """
    if type(entry) is not AuditEntry or not isinstance(operation, OperationContext):
        raise TypeError("La auditoría requiere una entrada y un contexto explícitos.")
    entry.__post_init__()
    event = AuditEvent.objects.create(
        actor_kind=entry.actor_kind.value,
        actor_account_id=entry.actor_account_id,
        context_kind=entry.context_kind.value,
        organization_id=entry.organization_id,
        academic_scope_id=entry.academic_scope_id,
        action_code=entry.action_code,
        resource_kind=entry.resource_kind,
        resource_id=entry.resource_id,
        occurred_at=operation.now(),
        reason=entry.reason.value if entry.reason else None,
        before_state=entry.before_state.to_dict() if entry.before_state is not None else None,
        after_state=entry.after_state.to_dict() if entry.after_state is not None else None,
        correlation_id=operation.correlation_id,
    )
    return AuditReceipt(
        event_id=event.pk, correlation_id=event.correlation_id, occurred_at=event.occurred_at
    )
