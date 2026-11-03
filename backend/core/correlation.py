"""Contexto técnico explícito, compartido por las llamadas de una operación."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self
from uuid import UUID

from core.clock import Clock, as_utc
from core.identifiers import new_id


@dataclass(frozen=True, slots=True)
class OperationContext:
    """No contiene actor, permisos, contactos ni un instante de autorización congelado."""

    correlation_id: UUID
    clock: Clock = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.correlation_id, UUID):
            raise TypeError("La correlación debe ser un UUID.")

    @classmethod
    def start(cls, *, clock: Clock) -> Self:
        """La entrada del servidor crea una correlación nueva para la operación."""
        return cls(correlation_id=new_id(), clock=clock)

    def now(self) -> datetime:
        """Consulta de nuevo el reloj; un permiso temporal debe usar el instante vigente."""
        return as_utc(self.clock.now())
