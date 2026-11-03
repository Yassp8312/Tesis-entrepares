"""Instantes UTC conscientes de zona, sin decisiones de calendario del producto."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def as_utc(instant: datetime) -> datetime:
    """Conserva el instante; rechaza valores sin un desplazamiento de zona definido."""
    if not isinstance(instant, datetime):
        raise TypeError("Se requiere un datetime consciente de zona.")
    if instant.utcoffset() is None:
        raise ValueError("Un instante sin zona no se puede interpretar como UTC.")
    return instant.astimezone(UTC)


class Clock(Protocol):
    """Dependencia temporal sustituible en el caso de aplicación."""

    def now(self) -> datetime:
        """Devuelve el instante actual consciente de zona, en UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Adaptador determinista; no modifica el reloj global, Django ni PostgreSQL."""

    instant: datetime

    def __post_init__(self):
        object.__setattr__(self, "instant", as_utc(self.instant))

    def now(self) -> datetime:
        return self.instant
