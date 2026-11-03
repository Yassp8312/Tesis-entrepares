"""Límite JSON incluso para errores del resolver o respuestas de Django en DEBUG."""

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from api.context import is_api_request, operation_context, stamp_response
from api.errors import json_error, log_unexpected

STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    406: "NOT_ACCEPTABLE",
    409: "STATE_CONFLICT",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "THROTTLED",
    503: "SERVICE_UNAVAILABLE",
}


class ApiBoundaryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if is_api_request(request):
            operation_context(request)

    def process_exception(self, request, exception):
        if not is_api_request(request):
            return None
        if isinstance(exception, Http404):
            code = "NOT_FOUND"
        elif isinstance(exception, PermissionDenied):
            code = "FORBIDDEN"
        elif isinstance(exception, SuspiciousOperation):
            code = "VALIDATION_ERROR"
        else:
            code = "INTERNAL_ERROR"
            log_unexpected(request, exception)
        return json_error(request, code)

    def process_response(self, request, response):
        if not is_api_request(request):
            return response
        if response.status_code >= 400 and not getattr(response, "api_error_normalized", False):
            replacement = json_error(
                request,
                STATUS_CODES.get(response.status_code, "INTERNAL_ERROR"),
            )
            for key, value in response.items():
                if key.lower() in {
                    "allow",
                    "retry-after",
                    "vary",
                    "x-frame-options",
                    "x-content-type-options",
                    "referrer-policy",
                    "cross-origin-opener-policy",
                    "strict-transport-security",
                    "content-security-policy",
                }:
                    replacement[key] = value
            replacement.cookies.update(response.cookies)
            response = replacement
        return stamp_response(request, response)
