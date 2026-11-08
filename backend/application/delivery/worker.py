"""Fases duraderas separadas: reclamar, validar/preparar, enviar, cerrar o recuperar."""

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from django.db import connection, transaction

from application.delivery.sources import DeliveryTemplate, lock_source, validate_source
from core.correlation import OperationContext
from modules.notifications.commands import delivery as commands
from modules.notifications.contracts.delivery import (
    DeliveryContext,
    DeliveryError,
    DeliveryResult,
    PreparedEmail,
    RenderedEmail,
    TransportResult,
    WorkerPolicy,
)
from modules.notifications.selectors.delivery import get_outbox_envelope, get_outbox_origin


@dataclass(frozen=True, slots=True)
class WorkerResult:
    status: str
    outbox_id: UUID | None = None
    recovered: int = 0


class OutboxWorker:
    def __init__(
        self, *, transport, templates: tuple[DeliveryTemplate, ...] = (), policy=WorkerPolicy()
    ):
        if (
            type(policy) is not WorkerPolicy
            or type(templates) is not tuple
            or any(type(t) is not DeliveryTemplate for t in templates)
        ):
            raise TypeError("El ejecutor requiere configuración explícita del servidor.")
        if (
            type(transport.supports_idempotency) is not bool
            or type(transport.timeout_seconds) is not int
            or not 1 <= transport.timeout_seconds < policy.lease_seconds
        ):
            raise ValueError(
                "El transporte debe declarar timeout menor al plazo y su idempotencia real."
            )
        registry = {template.key: template for template in templates}
        if len(registry) != len(templates):
            raise ValueError("No se admiten plantillas duplicadas.")
        self.templates, self.policy, self.transport = MappingProxyType(registry), policy, transport

    def _prepare(self, claim, operation):
        with transaction.atomic(durable=True):
            origin = get_outbox_origin(outbox_id=claim.outbox_id)
            source = lock_source(origin=origin, now=operation.now()) if origin else None
            now = operation.now()
            if not commands.lock_claim(claim=claim, now=now):
                return None, "stale"
            envelope = get_outbox_envelope(outbox_id=claim.outbox_id)
            error = None
            if envelope is None or envelope.origin != origin or source is None:
                error = DeliveryError.SOURCE_INVALID
            template = self.templates.get(envelope.template_key) if envelope else None
            if error is None and template is None:
                error = DeliveryError.TEMPLATE_UNAVAILABLE
            context = (
                validate_source(source=source, envelope=envelope, template=template, now=now)
                if error is None
                else error
            )
            if type(context) is DeliveryContext:
                try:
                    content = template.render(context)
                    if type(content) is not RenderedEmail:
                        raise TypeError("Resultado de plantilla incompatible.")
                    content.__post_init__()
                except Exception:
                    context = DeliveryError.RENDER_FAILED
            if type(context) is DeliveryContext:
                # El renderizado también pudo cruzar el vencimiento del origen.
                context = validate_source(
                    source=source, envelope=envelope, template=template, now=operation.now()
                )
            if type(context) is DeliveryContext:
                # No reutilizar una reclamación cuyo plazo se consumió al preparar.
                if not commands.lock_claim(claim=claim, now=operation.now()):
                    return None, "stale"
                return PreparedEmail(
                    claim.outbox_id, envelope.idempotency_key, envelope.destination, content
                ), "prepared"
            finished = commands.finish_claim(
                claim=claim,
                outcome=TransportResult(DeliveryResult.PERMANENT),
                policy=self.policy,
                now=operation.now(),
                error=context,
                cancel=context is DeliveryError.SOURCE_INVALID,
            )
            return None, (
                "cancelled" if context is DeliveryError.SOURCE_INVALID else "failed"
            ) if finished else "stale"

    def run_once(self, *, operation: OperationContext, recover_limit=50) -> WorkerResult:
        if connection.in_atomic_block:
            raise RuntimeError("El ejecutor no puede enviar desde una transacción exterior.")
        if not isinstance(operation, OperationContext):
            raise TypeError("El ejecutor requiere reloj y correlación explícitos.")
        with transaction.atomic(durable=True):
            recovered = commands.recover_expired(
                policy=self.policy, now=operation.now(), limit=recover_limit
            )
        with transaction.atomic(durable=True):
            claim = commands.claim_next(
                policy=self.policy,
                now=operation.now(),
                retry_unknown=self.policy.retry_unknown and self.transport.supports_idempotency,
            )
        if claim is None:
            return WorkerResult("empty", recovered=recovered)
        prepared, status = self._prepare(claim, operation)
        if prepared is None:
            return WorkerResult(status, claim.outbox_id, recovered)
        # Fuera de toda atomic: ni una caída del proceso ni un rollback pueden deshacer SMTP.
        try:
            result = self.transport.send(prepared)
            if type(result) is not TransportResult:
                result = TransportResult(DeliveryResult.UNKNOWN)
        except Exception:
            result = TransportResult(DeliveryResult.UNKNOWN)
        with transaction.atomic(durable=True):
            finished = commands.finish_claim(
                claim=claim, outcome=result, policy=self.policy, now=operation.now()
            )
        return WorkerResult(
            result.result.value if finished else "stale", claim.outbox_id, recovered
        )
