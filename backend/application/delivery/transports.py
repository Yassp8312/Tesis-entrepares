"""Adaptador Django intercambiable: resultado del canal, sin escribir persistencia."""

import smtplib

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.db import connection

from modules.notifications.contracts.delivery import (
    DeliveryResult,
    PreparedEmail,
    RenderedEmail,
    TransportResult,
)


class DjangoEmailTransport:
    supports_idempotency = False  # SMTP y Message-ID no garantizan deduplicación.

    def __init__(self, *, timeout_seconds=10):
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
            raise ValueError("El transporte requiere un timeout técnico acotado.")
        self.timeout_seconds = timeout_seconds

    def send(self, message: PreparedEmail) -> TransportResult:
        if connection.in_atomic_block:
            raise RuntimeError("El transporte externo debe ejecutarse después del commit.")
        if type(message) is not PreparedEmail or type(message.content) is not RenderedEmail:
            raise TypeError("El transporte requiere un mensaje interno preparado.")
        message.content.__post_init__()
        validate_email(message.destination)
        if settings.EMAIL_BACKEND not in {
            "django.core.mail.backends.smtp.EmailBackend",
            "django.core.mail.backends.locmem.EmailBackend",
        }:
            # Console/file backends podrían escribir enlaces o contenido privado en registros.
            return TransportResult(DeliveryResult.PERMANENT)
        try:
            with get_connection(fail_silently=False, timeout=self.timeout_seconds) as backend:
                mail = EmailMessage(
                    subject=message.content.subject,
                    body=message.content.body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[message.destination],
                    connection=backend,
                    headers={"X-Entrepares-Outbox": str(message.outbox_id)},
                )
                count = backend.send_messages([mail])
            return TransportResult(
                DeliveryResult.ACCEPTED if count == 1 else DeliveryResult.PERMANENT
            )
        except smtplib.SMTPRecipientsRefused as error:
            codes = [data[0] for data in error.recipients.values()]
            retryable = bool(codes) and all(
                type(code) is int and 400 <= code < 500 for code in codes
            )
            return TransportResult(
                DeliveryResult.TEMPORARY if retryable else DeliveryResult.PERMANENT
            )
        except smtplib.SMTPResponseException as error:
            return TransportResult(
                DeliveryResult.TEMPORARY
                if 400 <= error.smtp_code < 500
                else DeliveryResult.PERMANENT
            )
        except smtplib.SMTPNotSupportedError:
            return TransportResult(DeliveryResult.PERMANENT)
        except (OSError, smtplib.SMTPException):
            # Desconexión/timeout puede ocurrir después de que el servidor aceptara DATA.
            return TransportResult(DeliveryResult.UNKNOWN)
