"""Producción con secretos y destino de base configurados explícitamente."""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from config.environment import env_bool, env_list, env_string

from .base import *  # noqa: F403

DEBUG = False
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("django-insecure-", "test-only-")):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY no es apta para producción.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Producción requiere DJANGO_ALLOWED_HOSTS explícitos.")

for variable, field in [
    ("POSTGRES_DB", "NAME"),
    ("POSTGRES_USER", "USER"),
    ("POSTGRES_PASSWORD", "PASSWORD"),
    ("POSTGRES_HOST", "HOST"),
]:
    DATABASES["default"][field] = env_string(variable, required=True)  # noqa: F405

for origin in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or "*" in origin:
        raise ImproperlyConfigured("Los orígenes CSRF de producción deben ser HTTPS explícitos.")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER", False):
    # Activar solo cuando el proxy de despliegue sobrescriba este encabezado.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env_string("EMAIL_HOST")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env_string("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_string("EMAIL_HOST_PASSWORD")
