import json
import re
import warnings
from uuid import UUID, uuid4

import pytest
from django.http import HttpResponse
from django.middleware.csrf import get_token, rotate_token
from django.test import Client, override_settings
from django.urls import include, path
from rest_framework import exceptions, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.errors import ApiProblem, field_errors
from api.pagination import ContractPagination
from api.serializers import JSONSerializer, PageQuerySerializer, QueryBooleanField
from api.views import JSONAPIView

SECRET = "valor-sintetico-que-no-debe-aparecer-en-errores"


class ContactInput(JSONSerializer):
    value = serializers.CharField(max_length=30)


class PayloadInput(JSONSerializer):
    contacts = ContactInput(many=True, max_length=3)
    server_id = serializers.UUIDField(read_only=True)
    actor = serializers.HiddenField(default="solo-servidor")


class PayloadView(JSONAPIView):
    permission_classes = [AllowAny]
    input_serializer_class = PayloadInput

    def post(self, request):
        return Response({"accepted": True})


class TokenView(JSONAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request._request)})


class RotateView(JSONAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        rotate_token(request._request)
        return Response({"csrf_token": get_token(request._request)})


class RenderFailureView(JSONAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"private": SECRET, "not_serializable": object()})


class PageFilters(PageQuerySerializer):
    q = serializers.CharField(max_length=200, required=False)
    funded = QueryBooleanField(required=False)


class PageView(JSONAPIView):
    permission_classes = [AllowAny]
    query_serializer_class = PageFilters
    rows = list(range(1, 206))

    def get(self, request):
        paginator = ContractPagination()
        rows = paginator.paginate_queryset(self.rows, request, view=self)
        return paginator.get_paginated_response(rows)


class EmptyPageView(PageView):
    rows = []


class ProblemView(JSONAPIView):
    permission_classes = [AllowAny]

    def get(self, request, code):
        raise ApiProblem(code)


class ExceptionView(JSONAPIView):
    permission_classes = [AllowAny]

    def get(self, request, kind):
        error = {
            "unexpected": RuntimeError,
            "permission": exceptions.PermissionDenied,
            "credentials": exceptions.AuthenticationFailed,
            "missing": exceptions.NotFound,
        }[kind]
        raise error(SECRET)


class PrivateView(JSONAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"private": True})


class ThrottleView(JSONAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raise exceptions.Throttled(wait=2.2)


def plain_failure(request):
    raise RuntimeError(SECRET)


def plain_forbidden(request):
    return HttpResponse(SECRET, status=403)


urlpatterns = [
    path("api/v1/_tests/token/", TokenView.as_view()),
    path("api/v1/_tests/rotate/", RotateView.as_view()),
    path("api/v1/_tests/render-failure/", RenderFailureView.as_view()),
    path("api/v1/_tests/payload/", PayloadView.as_view()),
    path("api/v1/_tests/page/", PageView.as_view()),
    path("api/v1/_tests/empty/", EmptyPageView.as_view()),
    path("api/v1/_tests/problem/<str:code>/", ProblemView.as_view()),
    path("api/v1/_tests/exception/<str:kind>/", ExceptionView.as_view()),
    path("api/v1/_tests/private/", PrivateView.as_view()),
    path("api/v1/_tests/throttle/", ThrottleView.as_view()),
    path("api/v1/_tests/plain-failure/", plain_failure),
    path("api/v1/_tests/plain-forbidden/", plain_forbidden),
    path("", include("config.urls")),
]


@pytest.fixture(autouse=True)
def synthetic_routes(settings, tmp_path):
    settings.ROOT_URLCONF = __name__
    # Este ensayo no evalúa la colección estática de SP01-T09.
    settings.STATIC_ROOT = tmp_path


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True)


def csrf(browser):
    return {"HTTP_X_CSRFTOKEN": browser.get("/api/v1/_tests/token/").json()["csrf_token"]}


def assert_error(response, status, code):
    assert response.status_code == status
    assert response["Content-Type"].startswith("application/json")
    data = response.json()
    assert set(data) == {"code", "message", "fields", "request_id"}
    assert data["code"] == code and re.fullmatch(r"[A-Z][A-Z0-9_]*", code)
    assert 1 <= len(data["message"]) <= 1000 and len(data["fields"]) <= 100
    assert UUID(data["request_id"]).version == 4
    assert data["request_id"] == response["X-Request-ID"]
    assert response["Cache-Control"] == "no-store"
    assert SECRET not in response.content.decode()
    for field in data["fields"]:
        assert set(field) == {"path", "code", "message"}
        for key, maximum in [("path", 200), ("code", 80), ("message", 1000)]:
            assert field[key].strip() and 1 <= len(field[key]) <= maximum
    return data


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize(
    "url", ["/api", "/api/v1", "/api/v1/", "/api/v1/no-existe/", "/api/v2/no-existe/"]
)
def test_unknown_api_route_is_json_in_both_debug_modes(browser, settings, debug, url):
    settings.DEBUG = debug
    assert_error(browser.get(url, HTTP_ACCEPT="text/html"), 404, "NOT_FOUND")


def test_unknown_unsafe_route_has_no_mutation_and_keeps_json_404(browser):
    assert_error(
        browser.post("/api/v1/no-existe/", data="{}", content_type="application/json"),
        404,
        "NOT_FOUND",
    )


def test_correlation_is_generated_per_request_and_does_not_trust_client(browser):
    supplied = str(uuid4())
    first = browser.get("/api/v1/_tests/page/", HTTP_X_REQUEST_ID=supplied)
    second = browser.get("/api/v1/_tests/page/", HTTP_X_REQUEST_ID=supplied)
    assert first["X-Request-ID"] != supplied
    assert first["X-Request-ID"] != second["X-Request-ID"]
    assert first["Cache-Control"] == second["Cache-Control"] == "no-store"


@pytest.mark.parametrize("url", ["/otra-ruta/", "/apiary/"])
def test_non_api_urls_remain_outside_json_boundary(browser, url):
    response = browser.get(url)
    assert response.status_code == 404 and response["Content-Type"].startswith("text/html")
    assert "X-Request-ID" not in response


@pytest.mark.parametrize("key", ["is_superuser", "server_id", "actor"])
def test_unknown_readonly_and_hidden_fields_are_rejected(browser, key):
    response = browser.post(
        "/api/v1/_tests/payload/",
        {"contacts": [{"value": "válido"}], key: SECRET},
        content_type="application/json",
        **csrf(browser),
    )
    fields = assert_error(response, 400, "VALIDATION_ERROR")["fields"]
    assert fields == [{"path": key, "code": "unexpected_field", "message": "Campo no admitido."}]


def test_nested_errors_identify_list_indices_and_never_echo_values(browser):
    response = browser.post(
        "/api/v1/_tests/payload/",
        {"contacts": [{}, {"value": "válido", "is_verified": SECRET}]},
        content_type="application/json",
        **csrf(browser),
    )
    fields = assert_error(response, 400, "VALIDATION_ERROR")["fields"]
    assert {(f["path"], f["code"]) for f in fields} == {
        ("contacts[0].value", "required"),
        ("contacts[1].is_verified", "unexpected_field"),
    }


@pytest.mark.parametrize("as_dict", [True, False])
def test_drf_current_and_legacy_list_formats_produce_same_field_path(settings, as_dict):
    options = {**settings.REST_FRAMEWORK, "LIST_SERIALIZER_ERRORS_AS_DICT": as_dict}
    with override_settings(REST_FRAMEWORK=options), warnings.catch_warnings(record=True):
        serializer = ContactInput(data=[{"value": "correcto"}, {}], many=True)
        assert not serializer.is_valid()
        errors = field_errors(serializer.errors)
    assert [(field["path"], field["code"]) for field in errors] == [("$[1].value", "required")]


@pytest.mark.parametrize("body", ["[]", "null", '"texto"', "17"])
def test_object_input_rejects_other_json_root_types(browser, body):
    response = browser.post(
        "/api/v1/_tests/payload/", body, content_type="application/json", **csrf(browser)
    )
    assert_error(response, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "body",
    [
        '{"contacts":',
        '{"contacts": [], "contacts": []}',
        '{"contacts": [{"value": "uno", "value": "dos"}]}',
        '{"contacts": NaN}',
        '{"contacts": Infinity}',
        '{"contacts": 1e9999}',
    ],
)
def test_invalid_or_ambiguous_json_is_rejected_without_parser_details(browser, body):
    response = browser.post(
        "/api/v1/_tests/payload/", body, content_type="application/json", **csrf(browser)
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_non_json_input_and_unsupported_accept_use_normalized_errors(browser):
    assert_error(
        browser.post("/api/v1/_tests/payload/", "x=1", content_type="text/plain", **csrf(browser)),
        415,
        "UNSUPPORTED_MEDIA_TYPE",
    )
    assert_error(
        browser.get("/api/v1/_tests/page/", HTTP_ACCEPT="text/html"), 406, "NOT_ACCEPTABLE"
    )


def test_missing_csrf_is_rejected_even_without_session(browser):
    response = browser.post(
        "/api/v1/_tests/payload/", {"contacts": []}, content_type="application/json"
    )
    assert_error(response, 403, "CSRF_FAILED")


def test_valid_csrf_accepts_anonymous_mutation_but_bad_origin_or_token_does_not(browser):
    headers = csrf(browser)
    payload = {"contacts": [{"value": "sintético"}]}
    assert browser.post(
        "/api/v1/_tests/payload/", payload, content_type="application/json", **headers
    ).json() == {"accepted": True}
    assert_error(
        browser.post(
            "/api/v1/_tests/payload/",
            payload,
            content_type="application/json",
            HTTP_ORIGIN="https://ajeno.example.invalid",
            **headers,
        ),
        403,
        "CSRF_FAILED",
    )
    assert_error(
        browser.post(
            "/api/v1/_tests/payload/",
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN="a" * 64,
        ),
        403,
        "CSRF_FAILED",
    )


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=1.0",
        "page=1e2",
        "page=true",
        "page=",
        "page_size=0",
        "page_size=101",
        "page_size=1.5",
        "page=1&page=2",
        "q=" + "x" * 201,
        "q=",
        "funded=1",
        "funded=yes",
        "unexpected=true",
    ],
)
def test_invalid_repeated_and_unknown_query_parameters_are_rejected(browser, query):
    assert_error(browser.get("/api/v1/_tests/page/?" + query), 400, "VALIDATION_ERROR")


def test_pagination_defaults_limits_and_last_page(browser):
    first = browser.get("/api/v1/_tests/page/").json()
    assert first == {"count": 205, "page": 1, "page_size": 20, "results": list(range(1, 21))}
    last = browser.get("/api/v1/_tests/page/?page=3&page_size=100&funded=false").json()
    assert last == {"count": 205, "page": 3, "page_size": 100, "results": list(range(201, 206))}
    assert_error(browser.get("/api/v1/_tests/page/?page=12"), 400, "VALIDATION_ERROR")
    assert browser.get("/api/v1/_tests/empty/").json() == {
        "count": 0,
        "page": 1,
        "page_size": 20,
        "results": [],
    }


def test_anonymous_private_access_is_403_without_authentication_challenge(browser):
    response = browser.get("/api/v1/_tests/private/")
    assert_error(response, 403, "AUTH_REQUIRED")
    assert "WWW-Authenticate" not in response


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("permission", 403, "FORBIDDEN"),
        ("credentials", 403, "CREDENTIALS_INVALID"),
        ("missing", 404, "NOT_FOUND"),
    ],
)
def test_framework_errors_do_not_publish_arbitrary_messages(browser, kind, status, code):
    assert_error(browser.get(f"/api/v1/_tests/exception/{kind}/"), status, code)


@pytest.mark.parametrize(
    "code,status",
    [
        ("STATE_CONFLICT", 409),
        ("VERSION_CONFLICT", 409),
        ("POLICY_NOT_CONFIGURED", 503),
        ("SERVICE_UNAVAILABLE", 503),
    ],
)
def test_explicit_problems_preserve_contract_codes(browser, code, status):
    assert_error(browser.get(f"/api/v1/_tests/problem/{code}/"), status, code)


def test_method_and_throttle_errors_preserve_http_headers(browser):
    method = browser.post(
        "/api/v1/_tests/page/", "{}", content_type="application/json", **csrf(browser)
    )
    assert_error(method, 405, "METHOD_NOT_ALLOWED")
    assert "GET" in method["Allow"]
    throttled = browser.get("/api/v1/_tests/throttle/")
    assert_error(throttled, 429, "THROTTLED")
    assert throttled["Retry-After"] == "3"


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize(
    "url", ["/api/v1/_tests/exception/unexpected/", "/api/v1/_tests/plain-failure/"]
)
def test_unexpected_failures_are_generic_and_log_only_safe_metadata(
    browser, settings, caplog, debug, url
):
    settings.DEBUG = debug
    response = browser.get(url, HTTP_AUTHORIZATION="Bearer " + SECRET)
    assert_error(response, 500, "INTERNAL_ERROR")
    records = [r for r in caplog.records if r.name == "entrepares.api"]
    assert len(records) == 1 and records[0].request_id == response["X-Request-ID"]
    assert records[0].exception_type == "RuntimeError" and records[0].exc_info is None
    assert response["X-Request-ID"] in caplog.text
    assert SECRET not in caplog.text


def test_plain_django_error_response_is_normalized(browser):
    assert_error(browser.get("/api/v1/_tests/plain-forbidden/"), 403, "FORBIDDEN")


def test_field_error_projection_is_bounded_and_json_serializable():
    details = {
        "k" * 300 + str(i): [exceptions.ErrorDetail("m" * 2000, code="c" * 200)] for i in range(110)
    }
    result = field_errors(details)
    assert len(result) == 100
    assert all(
        len(row["path"]) == 200 and len(row["code"]) == 80 and len(row["message"]) == 1000
        for row in result
    )
    json.dumps(result)


def test_field_projection_remains_nonblank_after_truncation():
    detail = {" " * 201 + "x": [exceptions.ErrorDetail(" " * 1001 + "x", code=" " * 81 + "x")]}
    assert field_errors(detail) == [{"path": "$", "code": "invalid", "message": "Valor inválido."}]


def test_rotated_csrf_secret_invalidates_previous_token(browser):
    old = csrf(browser)
    new = browser.post(
        "/api/v1/_tests/rotate/", "{}", content_type="application/json", **old
    ).json()["csrf_token"]
    payload = {"contacts": [{"value": "sintético"}]}
    assert_error(
        browser.post("/api/v1/_tests/payload/", payload, content_type="application/json", **old),
        403,
        "CSRF_FAILED",
    )
    assert (
        browser.post(
            "/api/v1/_tests/payload/",
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=new,
        ).status_code
        == 200
    )


def test_secure_requests_require_trusted_origin_or_referer(browser):
    headers = csrf(browser)
    payload = {"contacts": [{"value": "sintético"}]}
    assert_error(
        browser.post(
            "/api/v1/_tests/payload/",
            payload,
            secure=True,
            content_type="application/json",
            **headers,
        ),
        403,
        "CSRF_FAILED",
    )
    assert (
        browser.post(
            "/api/v1/_tests/payload/",
            payload,
            secure=True,
            content_type="application/json",
            HTTP_REFERER="https://testserver/formulario",
            **headers,
        ).status_code
        == 200
    )


@pytest.mark.parametrize("debug", [True, False])
def test_rendering_failure_also_keeps_json_without_private_response_data(browser, settings, debug):
    settings.DEBUG = debug
    assert_error(browser.get("/api/v1/_tests/render-failure/"), 500, "INTERNAL_ERROR")


def test_plain_django_view_uses_json_csrf_failure(browser):
    assert_error(
        browser.post("/api/v1/_tests/plain-forbidden/", "{}", content_type="application/json"),
        403,
        "CSRF_FAILED",
    )
