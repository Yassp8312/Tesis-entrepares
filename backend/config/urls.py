"""Origen común: entrada API; las rutas Vue se incorporan en su incremento."""

from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt

from api.errors import json_error


@csrf_exempt
def api_not_found(request):
    # Esta respuesta no ejecuta mutaciones; mantiene el 404 para cualquier método.
    return json_error(request, "NOT_FOUND")


urlpatterns = [
    path("api/v1/", include("api.v1.urls", namespace="v1")),
    re_path(r"^api(?:/.*)?$", api_not_found),
]
