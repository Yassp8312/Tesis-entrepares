"""Contratos/adaptador sin PostgreSQL ni conexiones SMTP reales."""

import smtplib
from dataclasses import FrozenInstanceError
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core import mail
from django.test import override_settings

from application.delivery.sources import DeliveryTemplate
from application.delivery.transports import DjangoEmailTransport
from application.delivery.worker import OutboxWorker
from modules.notifications.contracts.delivery import (
    DeliveryResult,
    PreparedEmail,
    RenderedEmail,
    TransportResult,
    WorkerPolicy,
)


def prepared():
    return PreparedEmail(
        uuid4(),
        "synthetic-idempotency-key",
        "recipient@example.invalid",
        RenderedEmail("Entrepares", "Contenido sintético privado."),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"lease_seconds": 0},
        {"lease_seconds": True},
        {"max_attempts": 0},
        {"max_attempts": 101},
        {"retry_seconds": 0},
        {"max_retry_seconds": 10, "retry_seconds": 11},
        {"retry_unknown": "yes"},
    ],
)
def test_policy_rejects_ambiguous_unbounded_or_incoherent_values(change):
    with pytest.raises(ValueError):
        WorkerPolicy(**change)


def test_backoff_is_bounded_without_building_huge_powers():
    policy = WorkerPolicy()
    assert policy.delay(1) == timedelta(seconds=30)
    assert policy.delay(2) == timedelta(seconds=60)
    assert policy.delay(2_147_483_647) == timedelta(seconds=3600)
    with pytest.raises(ValueError):
        policy.delay(True)


@pytest.mark.parametrize(
    "content",
    [
        ("", "texto"),
        ("cabecera\r\nBcc: forbidden@example.invalid", "texto"),
        ("a" * 201, "texto"),
        ("válido", ""),
        ("válido", "a" * 200001),
    ],
)
def test_rendered_content_rejects_headers_and_unbounded_payload(content):
    with pytest.raises(ValueError):
        RenderedEmail(*content)


def test_private_fields_are_immutable_and_not_in_repr():
    message = prepared()
    assert "recipient@" not in repr(message) and "privado" not in repr(message)
    assert "synthetic-idempotency-key" not in repr(message)
    with pytest.raises(FrozenInstanceError):
        message.destination = "other@example.invalid"
    with pytest.raises(TypeError):
        TransportResult("accepted")
    with pytest.raises(TypeError):
        TransportResult(DeliveryResult.ACCEPTED, "raw-provider-email@example.invalid")


@pytest.mark.parametrize(
    "changes",
    [
        {"key": "transaction_sample.email_confirmation"},
        {"key_versions": frozenset({"sample-only"})},
        {"purpose": "other"},
        {"key_versions": frozenset()},
        {"render": None},
    ],
)
def test_template_requires_explicit_purpose_and_real_versions(changes):
    values = dict(
        key="synthetic.confirmation",
        source_kind="challenge",
        render=lambda context: RenderedEmail("Asunto", "Texto"),
        purpose="email_confirmation",
        key_versions=frozenset({"v1"}),
    )
    with pytest.raises(ValueError):
        DeliveryTemplate(**{**values, **changes})


def test_worker_validates_transport_timeout_idempotency_and_unique_registry():
    transport = SimpleNamespace(supports_idempotency=False, timeout_seconds=120)
    with pytest.raises(ValueError):
        OutboxWorker(transport=transport)
    transport.timeout_seconds = 10
    transport.supports_idempotency = "yes"
    with pytest.raises(ValueError):
        OutboxWorker(transport=transport)
    transport.supports_idempotency = False
    template = DeliveryTemplate(
        "synthetic.notice", "notice", lambda context: RenderedEmail("Asunto", "Texto")
    )
    with pytest.raises(ValueError):
        OutboxWorker(transport=transport, templates=(template, template))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_django_adapter_accepts_one_recipient_without_dumping_content():
    adapter, message = DjangoEmailTransport(), prepared()
    result = adapter.send(message)
    assert result.result is DeliveryResult.ACCEPTED
    delivered = mail.outbox[-1]
    assert delivered.to == [message.destination] and delivered.cc == [] and delivered.bcc == []
    assert delivered.extra_headers == {"X-Entrepares-Outbox": str(message.outbox_id)}
    assert adapter.supports_idempotency is False


@pytest.mark.parametrize("backend", ["console", "filebased", "dummy"])
def test_adaptor_never_uses_backend_that_could_dump_private_messages(backend, capsys):
    with override_settings(EMAIL_BACKEND=f"django.core.mail.backends.{backend}.EmailBackend"):
        assert DjangoEmailTransport().send(prepared()).result is DeliveryResult.PERMANENT
    assert "privado" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "error,expected",
    [
        (smtplib.SMTPResponseException(450, b"private-synthetic"), DeliveryResult.TEMPORARY),
        (smtplib.SMTPResponseException(550, b"private-synthetic"), DeliveryResult.PERMANENT),
        (
            smtplib.SMTPRecipientsRefused({"private@example.invalid": (450, b"raw")}),
            DeliveryResult.TEMPORARY,
        ),
        (
            smtplib.SMTPRecipientsRefused({"private@example.invalid": (550, b"raw")}),
            DeliveryResult.PERMANENT,
        ),
        (smtplib.SMTPServerDisconnected("private-synthetic"), DeliveryResult.UNKNOWN),
        (TimeoutError("private-synthetic"), DeliveryResult.UNKNOWN),
        (smtplib.SMTPNotSupportedError("private-synthetic"), DeliveryResult.PERMANENT),
    ],
)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
def test_smtp_classification_does_not_return_provider_text(error, expected, monkeypatch):
    class Backend:
        def __enter__(self):
            raise error

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "application.delivery.transports.get_connection", lambda **kwargs: Backend()
    )
    result = DjangoEmailTransport().send(prepared())
    assert result.result is expected and "private" not in repr(result)
