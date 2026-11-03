"""Correlación de servidor para la adaptación HTTP."""

from core.clock import SystemClock
from core.correlation import OperationContext


def operation_context(request):
    raw = getattr(request, "_request", request)
    if not isinstance(getattr(raw, "operation_context", None), OperationContext):
        raw.operation_context = OperationContext.start(clock=SystemClock())
    return raw.operation_context


def is_api_request(request):
    return request.path_info == "/api" or request.path_info.startswith("/api/")


def stamp_response(request, response):
    response["X-Request-ID"] = str(operation_context(request).correlation_id)
    response["Cache-Control"] = "no-store"
    return response
