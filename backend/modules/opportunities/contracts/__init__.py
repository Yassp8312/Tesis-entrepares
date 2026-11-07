"""Tipos de intercambio de M05; sin modelos ORM, HTTP ni reglas de otros módulos."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OpportunityFundingState:
    opportunity_id: UUID
    is_funded: bool
