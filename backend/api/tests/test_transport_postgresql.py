import pytest
from django.test import Client

from api.tests.test_transport import assert_error, csrf
from modules.identity.models import Account

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def synthetic_routes(settings, tmp_path):
    settings.ROOT_URLCONF = "api.tests.test_transport"
    settings.STATIC_ROOT = tmp_path


def test_real_session_still_requires_csrf_for_mutation():
    account = Account.objects.create_user("sesion-http@example.org", "Muestra#72-Ciencia#Mar")
    browser = Client(enforce_csrf_checks=True)
    # Se prepara una sesión real de Django; el endpoint de login aún no está implementado.
    browser.force_login(account, backend="config.authentication.EmailBackend")
    assert browser.get("/api/v1/_tests/private/").json() == {"private": True}
    payload = {"contacts": [{"value": "sintético"}]}
    assert_error(
        browser.post("/api/v1/_tests/payload/", payload, content_type="application/json"),
        403,
        "CSRF_FAILED",
    )
    response = browser.post(
        "/api/v1/_tests/payload/", payload, content_type="application/json", **csrf(browser)
    )
    assert response.status_code == 200


def test_disabled_account_does_not_keep_private_access_through_old_session():
    account = Account.objects.create_user("deshabilitada@example.org", "Muestra#72-Ciencia#Mar")
    browser = Client(enforce_csrf_checks=True)
    browser.force_login(account, backend="config.authentication.EmailBackend")
    account.is_active = False
    account.save(update_fields=["is_active"])
    assert_error(browser.get("/api/v1/_tests/private/"), 403, "AUTH_REQUIRED")
