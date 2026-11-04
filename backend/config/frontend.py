"""Entrega del documento Vue y política de sus recursos compilados."""

import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import get_conditional_response, patch_cache_control, patch_vary_headers
from django.views.decorators.http import require_safe


def web_error(status, message):
    response = HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


def reserved_not_found(request):
    return web_error(404, "No se encontró el recurso solicitado.")


@require_safe
def frontend_document(request, route=""):
    # El destino se configura en el servidor; la ruta solicitada nunca es un archivo a abrir.
    if any(part.startswith(".") for part in route.split("/")) or PurePosixPath(route).suffix:
        return reserved_not_found(request)
    if not request.accepts("text/html"):
        return web_error(406, "Esta dirección corresponde a una página HTML.")
    try:
        content = Path(settings.FRONTEND_INDEX).read_bytes()
    except OSError:
        return web_error(503, "La interfaz está temporalmente fuera de servicio.")
    etag = f'"{sha256(content).hexdigest()}"'
    response = HttpResponse(
        content if request.method == "GET" else b"", content_type="text/html; charset=utf-8"
    )
    response["ETag"] = etag
    response["Content-Length"] = str(len(content))
    patch_cache_control(response, no_cache=True, max_age=0, must_revalidate=True)
    patch_vary_headers(response, ["Accept"])
    return get_conditional_response(request, etag=etag, response=response)


@lru_cache(maxsize=4)
def versioned_urls(manifest_path):
    # Artefacto del build, no datos de personas. Reiniciar WSGI después de preparar una versión.
    try:
        values = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        return frozenset()
    return frozenset(values)


def immutable_frontend_file(path, url):
    return url in versioned_urls(str(settings.FRONTEND_ASSET_MANIFEST))


def frontend_static_headers(headers, path, url):
    if immutable_frontend_file(path, url):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
