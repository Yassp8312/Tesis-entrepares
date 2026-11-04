import gzip
import json

import pytest
from django.core.management import call_command
from django.test import Client, override_settings

from config.frontend import immutable_frontend_file
from config.web_build import prepare_frontend

DOCUMENT = b'<!doctype html><html lang="es"><body><div id="app"></div></body></html>'


@pytest.fixture
def web(tmp_path, settings):
    index = tmp_path / "index.html"
    index.write_bytes(DOCUMENT)
    settings.FRONTEND_INDEX = index
    settings.FRONTEND_ASSET_MANIFEST = tmp_path / "versioned-assets.json"
    settings.STATIC_ROOT = tmp_path / "collected"
    settings.STATIC_ROOT.mkdir()
    settings.WHITENOISE_AUTOREFRESH = False
    return index


@pytest.mark.parametrize("route", ["/", "/acerca-de", "/personas/ejemplo", "/no-existe"])
def test_navigation_returns_same_document_without_database(web, client, route):
    response = client.get(route, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    assert response.content == DOCUMENT
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    assert response["Vary"] == "Accept"
    assert not response.cookies
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"


def test_document_revalidates_and_detects_new_build(web, client):
    first = client.get("/")
    cached = client.get("/acerca-de", HTTP_IF_NONE_MATCH=first["ETag"])
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached["ETag"] == first["ETag"]
    assert "no-cache" in cached["Cache-Control"]
    assert cached["Vary"] == "Accept"
    web.write_bytes(DOCUMENT.replace(b"app", b"nueva-version"))
    updated = client.get("/", HTTP_IF_NONE_MATCH=first["ETag"])
    assert updated.status_code == 200
    assert updated["ETag"] != first["ETag"]
    assert b"nueva-version" in updated.content


def test_head_conditional_and_unsafe_methods(web, client):
    get = client.get("/")
    head = client.head("/acerca-de")
    assert head.status_code == 200
    assert head.content == b""
    assert head["ETag"] == get["ETag"]
    assert head["Content-Length"] == str(len(DOCUMENT))
    assert client.head("/", HTTP_IF_NONE_MATCH=get["ETag"]).status_code == 304
    assert client.get("/", HTTP_IF_NONE_MATCH="*").status_code == 304
    for method in ["post", "put", "patch", "delete"]:
        response = getattr(client, method)("/acerca-de")
        assert response.status_code == 405
        assert set(response["Allow"].split(", ")) == {"GET", "HEAD"}
        assert DOCUMENT not in response.content


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("route", ["/api", "/api/", "/api/v1/inexistente/", "/api/inexistente"])
def test_api_never_becomes_frontend(web, route, debug):
    with override_settings(DEBUG=debug):
        response = Client().get(route, HTTP_ACCEPT="text/html")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["code"] == "NOT_FOUND"
    assert response["X-Request-ID"] == response.json()["request_id"]
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize(
    "route",
    [
        "/admin",
        "/admin/",
        "/admin/ejemplo",
        "/static",
        "/static/",
        "/static/ausente.js",
        "/.env",
        "/.git/config",
        "/favicon.ico",
        "/assets/ausente.js",
        "/archivo.js.map",
    ],
)
def test_reserved_and_missing_files_do_not_receive_document(web, client, route):
    response = client.get(route)
    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/plain")
    assert response["Cache-Control"] == "no-store"
    assert DOCUMENT not in response.content


def test_prefix_similar_to_reserved_is_valid_navigation(web, client):
    for route in ["/apiario", "/administracion", "/statico"]:
        assert client.get(route).content == DOCUMENT


def test_missing_build_is_controlled_and_does_not_affect_api(web, client):
    web.unlink()
    response = client.get("/")
    assert response.status_code == 503
    assert response["Cache-Control"] == "no-store"
    assert str(web).encode() not in response.content
    assert client.get("/api/v1/ausente/").json()["code"] == "NOT_FOUND"


def test_json_request_does_not_receive_html(web, client):
    response = client.get("/acerca-de", HTTP_ACCEPT="application/json")
    assert response.status_code == 406
    assert DOCUMENT not in response.content
    assert response["Cache-Control"] == "no-store"


def synthetic_build(source):
    (source / ".vite").mkdir(parents=True)
    (source / "assets").mkdir()
    (source / "licenses").mkdir()
    (source / "assets/main-abcdefgh.js").write_text('import("./lazy-12345678.js");')
    (source / "assets/lazy-12345678.js").write_text("export default 1;")
    (source / "assets/main-abcdefgh.css").write_text("body { color: #172e3a; }" * 100)
    (source / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (source / "licenses/example.txt").write_text("Licencia sintética de prueba")
    manifest = {
        "index.html": {
            "isEntry": True,
            "file": "assets/main-abcdefgh.js",
            "css": ["assets/main-abcdefgh.css"],
            "dynamicImports": ["lazy"],
        },
        "lazy": {"file": "assets/lazy-12345678.js"},
    }
    (source / ".vite/manifest.json").write_text(json.dumps(manifest))
    (source / "index.html").write_text(
        '<html><link rel="icon" href="/static/entrepares/favicon.svg"><script src="/static/entrepares/assets/main-abcdefgh.js"></script></html>'
    )


def test_prepare_build_preserves_modules_and_keeps_document_private(tmp_path):
    source, target = tmp_path / "dist", tmp_path / "prepared"
    synthetic_build(source)
    assert prepare_frontend(source, target) == {"public_files": 5, "versioned_assets": 3}
    assert (target / "index.html").read_bytes() == (source / "index.html").read_bytes()
    public = target / "static/entrepares"
    assert not (public / "index.html").exists()
    assert not (public / ".vite").exists()
    for name in ["assets/main-abcdefgh.js", "assets/lazy-12345678.js", "licenses/example.txt"]:
        assert (public / name).read_bytes() == (source / name).read_bytes()
    assert len(json.loads((target / "versioned-assets.json").read_text())) == 3


@pytest.mark.parametrize(
    "failure", ["missing_module", "external_url", "path_traversal", "unversioned", "missing_import"]
)
def test_incomplete_build_does_not_replace_previous_document(tmp_path, failure):
    source, target = tmp_path / "dist", tmp_path / "prepared"
    synthetic_build(source)
    target.mkdir()
    (target / "index.html").write_bytes(DOCUMENT)
    manifest_file = source / ".vite/manifest.json"
    manifest = json.loads(manifest_file.read_text())
    if failure == "missing_module":
        (source / "assets/lazy-12345678.js").unlink()
    elif failure == "external_url":
        (source / "index.html").write_text('<script src="https://example.org/main.js"></script>')
    elif failure == "path_traversal":
        manifest["lazy"]["file"] = "../private.js"
    elif failure == "unversioned":
        (source / "assets/lazy.js").write_text("export default 1;")
        manifest["lazy"]["file"] = "assets/lazy.js"
    else:
        manifest["index.html"]["dynamicImports"] = ["missing"]
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        prepare_frontend(source, target)
    assert (target / "index.html").read_bytes() == DOCUMENT
    assert not (target / "static").exists()


def test_collectstatic_and_whitenoise_keep_vite_bytes_caching_and_compression(tmp_path, settings):
    source, target = tmp_path / "dist", tmp_path / "prepared"
    synthetic_build(source)
    prepare_frontend(source, target)
    settings.FRONTEND_INDEX = target / "index.html"
    settings.FRONTEND_ASSET_MANIFEST = target / "versioned-assets.json"
    settings.STATIC_ROOT = tmp_path / "collected"
    settings.STATICFILES_DIRS = [("entrepares", target / "static/entrepares")]
    settings.WHITENOISE_AUTOREFRESH = False
    call_command("collectstatic", interactive=False, verbosity=0)
    client = Client()
    url = "/static/entrepares/assets/main-abcdefgh.css"
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/css")
    assert response["Cache-Control"] == "public, max-age=31536000, immutable"
    assert (
        b"".join(response.streaming_content) == (source / "assets/main-abcdefgh.css").read_bytes()
    )
    assert "Access-Control-Allow-Origin" not in response
    assert client.get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code == 304
    compressed = client.get(url, HTTP_ACCEPT_ENCODING="gzip")
    assert compressed["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in compressed["Vary"]
    assert (
        gzip.decompress(b"".join(compressed.streaming_content))
        == (source / "assets/main-abcdefgh.css").read_bytes()
    )
    head = client.head(url)
    assert head.status_code == 200
    assert b"".join(head.streaming_content) == b""
    rejected = client.post(url)
    assert rejected.status_code == 405
    assert b"".join(rejected.streaming_content) == b""
    for path in ["favicon.svg", "licenses/example.txt"]:
        response = client.get("/static/entrepares/" + path)
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
        assert b"".join(response.streaming_content) == (source / path).read_bytes()
    for path in ["index.html", ".vite/manifest.json", "ausente.js"]:
        assert client.get("/static/entrepares/" + path).status_code == 404
    assert not immutable_frontend_file("unused", "/static/entrepares/assets/falso-abcdefgh.js")
    assert client.get("/acerca-de").status_code == 200
