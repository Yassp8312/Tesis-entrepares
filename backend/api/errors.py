"""Errores de transporte acotados; las excepciones internas no se publican."""

import logging
from collections.abc import Mapping
from itertools import islice
from math import ceil

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import SuspiciousOperation
from django.http import Http404, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import set_rollback

from api.context import is_api_request, operation_context, stamp_response

LOGGER = logging.getLogger("entrepares.api")
ERRORS = {
    "VALIDATION_ERROR": (400, "Los datos enviados no son válidos."),
    "AUTH_REQUIRED": (403, "Debes iniciar sesión para realizar esta operación."),
    "CREDENTIALS_INVALID": (403, "Las credenciales no son válidas."),
    "CSRF_FAILED": (
        403,
        "No se pudo verificar la solicitud. Actualiza la página e inténtalo de nuevo.",
    ),
    "FORBIDDEN": (403, "No tienes permiso para realizar esta operación."),
    "NOT_FOUND": (404, "No se encontró el recurso solicitado."),
    "METHOD_NOT_ALLOWED": (405, "El método no está permitido para esta ruta."),
    "NOT_ACCEPTABLE": (406, "La API devuelve contenido application/json."),
    "STATE_CONFLICT": (409, "El estado actual no permite completar la operación."),
    "VERSION_CONFLICT": (409, "Los datos cambiaron. Actualízalos antes de continuar."),
    "UNSUPPORTED_MEDIA_TYPE": (415, "El cuerpo de la solicitud debe usar application/json."),
    "THROTTLED": (429, "Se alcanzó el límite de solicitudes. Inténtalo más tarde."),
    "INTERNAL_ERROR": (500, "No se pudo completar la operación."),
    "POLICY_NOT_CONFIGURED": (
        503,
        "La operación requiere una política que aún no está configurada.",
    ),
    "SERVICE_UNAVAILABLE": (503, "El servicio no está disponible temporalmente."),
}


class ApiProblem(exceptions.APIException):
    """Problema HTTP explícito; no recibe mensajes arbitrarios ni decide permisos."""

    def __init__(self, code):
        self.problem_code = code
        self.status_code, message = ERRORS[code]
        super().__init__(message, code=code.lower())


def field_errors(detail):
    def bounded(value, limit, fallback):
        text = str(value)[:limit]
        return text if text.strip() else fallback

    def walk(value, path=""):
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key == api_settings.NON_FIELD_ERRORS_KEY:
                    child_path = path
                elif isinstance(key, int) or str(key).isdecimal():
                    child_path = f"{path or '$'}[{key}]"
                else:
                    child_path = f"{path}.{key}" if path else str(key)
                yield from walk(child, child_path)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                child_path = (
                    f"{path or '$'}[{index}]" if isinstance(child, (Mapping, list)) else path
                )
                yield from walk(child, child_path)
        else:
            yield {
                "path": bounded(path, 200, "$"),
                "code": bounded(getattr(value, "code", "invalid"), 80, "invalid"),
                "message": bounded(value, 1000, "Valor inválido."),
            }

    return list(islice(walk(detail), 100))


def error_payload(request, code, *, fields=()):
    return {
        "code": code,
        "message": ERRORS[code][1],
        "fields": list(fields),
        "request_id": str(operation_context(request).correlation_id),
    }


def json_error(request, code, *, status=None):
    response = JsonResponse(error_payload(request, code), status=status or ERRORS[code][0])
    response.api_error_normalized = True
    return stamp_response(request, response)


def log_unexpected(request, exception):
    # No registrar mensaje de excepción, cuerpo, URL, cabeceras ni traza con datos.
    request_id = str(operation_context(request).correlation_id)
    exception_type = type(exception).__name__
    LOGGER.error(
        "Fallo interno de API request_id=%s exception_type=%s",
        request_id,
        exception_type,
        extra={
            "request_id": request_id,
            "exception_type": exception_type,
        },
    )


def exception_handler(exception, context):
    request = context["request"]
    fields = []
    if isinstance(exception, ApiProblem):
        code = exception.problem_code
    elif isinstance(exception, exceptions.ValidationError):
        code, fields = "VALIDATION_ERROR", field_errors(exception.detail)
    elif isinstance(exception, exceptions.ParseError | SuspiciousOperation):
        code = "VALIDATION_ERROR"
    elif isinstance(exception, exceptions.NotAuthenticated):
        code = "AUTH_REQUIRED"
    elif isinstance(exception, exceptions.AuthenticationFailed):
        code = "CREDENTIALS_INVALID"
    elif isinstance(exception, exceptions.PermissionDenied | DjangoPermissionDenied):
        code = "FORBIDDEN"
    elif isinstance(exception, exceptions.NotFound | Http404):
        code = "NOT_FOUND"
    elif isinstance(exception, exceptions.MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"
    elif isinstance(exception, exceptions.NotAcceptable):
        code = "NOT_ACCEPTABLE"
    elif isinstance(exception, exceptions.UnsupportedMediaType):
        code = "UNSUPPORTED_MEDIA_TYPE"
    elif isinstance(exception, exceptions.Throttled):
        code = "THROTTLED"
    else:
        code = "INTERNAL_ERROR"
        log_unexpected(request, exception)
    set_rollback()
    response = Response(error_payload(request, code, fields=fields), status=ERRORS[code][0])
    if isinstance(exception, exceptions.Throttled) and exception.wait is not None:
        response["Retry-After"] = str(max(0, ceil(exception.wait)))
    response.api_error_normalized = True
    return stamp_response(request, response)


def csrf_failure(request, reason=""):
    if is_api_request(request):
        return json_error(request, "CSRF_FAILED")
    from django.views.csrf import csrf_failure as django_csrf_failure

    return django_csrf_failure(request, reason=reason)
