"""Revalidación de origen con anclas antes de bloquear la salida, sin ORM ajeno."""

import json
from dataclasses import dataclass, field
from typing import Callable
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from modules.identity.contracts import LockedAccountState
from modules.identity.contracts.delivery import ChallengeDeliveryState
from modules.identity.selectors import lock_account_states
from modules.identity.selectors.delivery import get_challenge_owner, lock_delivery_challenge
from modules.notifications.contracts.delivery import (
    DeliveryContext,
    DeliveryError,
    NoticeDeliveryState,
    RenderedEmail,
)
from modules.notifications.selectors.delivery import get_notice_opportunity, lock_notice
from modules.opportunities.contracts.delivery import OpportunityDeliveryState
from modules.opportunities.selectors.delivery import get_delivery_owner, lock_delivery_opportunity
from modules.organizations.selectors.delivery import lock_delivery_organization


@dataclass(frozen=True, slots=True)
class DeliveryTemplate:
    key: str
    source_kind: str
    render: Callable[[DeliveryContext], RenderedEmail] = field(repr=False)
    purpose: str | None = None
    key_versions: frozenset[str] = frozenset()

    def __post_init__(self):
        if (
            type(self.key) is not str
            or not self.key
            or len(self.key) > 80
            or not callable(self.render)
            or self.source_kind not in ("challenge", "notice")
        ):
            raise ValueError("La plantilla debe ser una configuración explícita del servidor.")
        if type(self.key_versions) is not frozenset or any(
            type(key) is not str for key in self.key_versions
        ):
            raise TypeError("Las versiones de firma deben ser explícitas e inmutables.")
        if self.source_kind == "challenge" and (
            self.purpose not in ("email_confirmation", "password_reset") or not self.key_versions
        ):
            raise ValueError(
                "La plantilla de identidad requiere finalidad y versiones acreditadas."
            )
        if "sample-only" in self.key_versions or self.key.startswith("transaction_sample."):
            raise ValueError("Los ejemplos transaccionales no son plantillas de envío.")


@dataclass(frozen=True, slots=True)
class SourceState:
    recipient: LockedAccountState | None
    challenge: ChallengeDeliveryState | None = None
    opportunity: OpportunityDeliveryState | None = None
    notice: NoticeDeliveryState | None = None
    organization_id: UUID | None = None


def lock_source(*, origin, now) -> SourceState:
    """El origen es una pista no bloqueada: se compara de nuevo tras obtener anclas."""
    owner_id = (
        get_challenge_owner(challenge_id=origin.challenge_id) if origin.challenge_id else None
    )
    ids = tuple(
        identifier
        for identifier in (origin.recipient_account_id, owner_id)
        if identifier is not None
    )
    accounts = lock_account_states(account_ids=ids) if ids else ()
    recipient = next(
        (item for item in accounts if item.account_id == origin.recipient_account_id), None
    )
    challenge = opportunity = notice = None
    organization_id = None
    if origin.challenge_id and owner_id:
        challenge = lock_delivery_challenge(challenge_id=origin.challenge_id, account_id=owner_id)
    if origin.notice_id:
        opportunity_id = get_notice_opportunity(notice_id=origin.notice_id)
        owners = get_delivery_owner(opportunity_id=opportunity_id) if opportunity_id else None
        if owners and owners[1]:
            organization_id = owners[1]
            # Conserva el bloqueo aun cuando el resultado sea falso; se reevalúa después.
            lock_delivery_organization(
                organization_id=organization_id, account_id=origin.recipient_account_id, now=now
            )
        opportunity = (
            lock_delivery_opportunity(opportunity_id=opportunity_id) if opportunity_id else None
        )
        notice = lock_notice(notice_id=origin.notice_id)
    return SourceState(recipient, challenge, opportunity, notice, organization_id)


def validate_source(*, source, envelope, template: DeliveryTemplate, now):
    recipient = source.recipient
    if (
        recipient is None
        or not recipient.is_active
        or envelope.channel != "email"
        or envelope.destination != recipient.email
    ):
        return DeliveryError.SOURCE_INVALID
    try:
        validate_email(envelope.destination)
        payload = json.loads(envelope.payload_json)
    except (ValueError, TypeError, ValidationError):
        # No se propaga el contenido de un destino o payload privado al registro.
        return DeliveryError.UNSAFE_PAYLOAD
    if type(payload) is not dict:
        return DeliveryError.UNSAFE_PAYLOAD
    origin = envelope.origin
    if template.source_kind == "challenge":
        challenge = source.challenge
        if (
            challenge is None
            or origin.notice_id is not None
            or challenge.account_id != recipient.account_id
            or challenge.challenge_id != origin.challenge_id
            or challenge.email_snapshot != recipient.email
            or challenge.purpose != template.purpose
            or challenge.key_version not in template.key_versions
            or challenge.key_version == "sample-only"
            or challenge.consumed_at is not None
            or challenge.invalidated_at is not None
            or challenge.expires_at <= now
        ):
            return DeliveryError.SOURCE_INVALID
        if payload != {"challenge_id": str(challenge.challenge_id)}:
            return DeliveryError.UNSAFE_PAYLOAD
        return DeliveryContext(
            origin.outbox_id,
            challenge.challenge_id,
            "challenge",
            challenge.purpose,
            challenge.key_version,
        )
    notice, opportunity = source.notice, source.opportunity
    if (
        notice is None
        or opportunity is None
        or origin.challenge_id is not None
        or notice.notice_id != origin.notice_id
        or notice.opportunity_id != opportunity.opportunity_id
        or notice.cancelled_at is not None
        or notice.channel != "email"
        or notice.scheduled_for > now
        or notice.validity_revision != opportunity.validity_revision
        or opportunity.lifecycle != "active"
        or opportunity.visibility != "visible"
        or opportunity.expires_at is None
        or opportunity.expires_at <= now
        or opportunity.published_at is None
        or opportunity.published_at > now
    ):
        return DeliveryError.SOURCE_INVALID
    if opportunity.owner_account_id is not None:
        if opportunity.owner_account_id != recipient.account_id:
            return DeliveryError.SOURCE_INVALID
    elif (
        opportunity.owner_organization_id != source.organization_id
        or not lock_delivery_organization(
            organization_id=source.organization_id, account_id=recipient.account_id, now=now
        )
    ):
        return DeliveryError.SOURCE_INVALID
    expected = {
        "notice_id": str(notice.notice_id),
        "opportunity_id": str(opportunity.opportunity_id),
        "validity_revision": notice.validity_revision,
    }
    if payload != expected or type(payload.get("validity_revision")) is not int:
        return DeliveryError.UNSAFE_PAYLOAD
    return DeliveryContext(
        origin.outbox_id,
        notice.notice_id,
        "notice",
        opportunity_id=opportunity.opportunity_id,
        validity_revision=opportunity.validity_revision,
    )
