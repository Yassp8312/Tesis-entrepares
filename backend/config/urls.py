"""Origen común: API reservada y retorno HTML de navegación Vue."""

from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt

from api.errors import json_error
from config.frontend import frontend_document, reserved_not_found


@csrf_exempt
def api_not_found(request):
    # Esta respuesta no ejecuta mutaciones; mantiene el 404 para cualquier método.
    return json_error(request, "NOT_FOUND")


urlpatterns = [
    path("api/v1/", include("api.v1.urls", namespace="v1")),
    re_path(r"^api(?:/.*)?$", api_not_found),
    re_path(r"^(?:admin|static)(?:/.*)?$", reserved_not_found),
    re_path(r"^(?P<route>.*)$", frontend_document, name="frontend"),
]
