"""Configuración común; las credenciales proceden del entorno de proceso."""

from pathlib import Path

from config.environment import database_port, env_list, env_string
from config.frontend import frontend_static_headers, immutable_frontend_file

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BASE_DIR.parent

SECRET_KEY = env_string("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ("localhost", "127.0.0.1", "[::1]"))

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "modules.identity.apps.IdentityConfig",
    "modules.profiles.apps.ProfilesConfig",
    "modules.academics.apps.AcademicsConfig",
    "modules.organizations.apps.OrganizationsConfig",
]
MIDDLEWARE = [
    "api.middleware.ApiBoundaryMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_string("POSTGRES_DB", "entrepares_development"),
        "USER": env_string("POSTGRES_USER", "entrepares"),
        "PASSWORD": env_string("POSTGRES_PASSWORD"),
        "HOST": env_string("POSTGRES_HOST", "127.0.0.1"),
        "PORT": database_port(),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}

AUTH_USER_MODEL = "identity.Account"
AUTHENTICATION_BACKENDS = ["config.authentication.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# La unicidad funcional lower(email) se comprueba en identity.E001.
# El chequeo genérico de Django solo reconoce aquí la unicidad del campo sin función.
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["api.permissions.DenyUnconfiguredAccess"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["api.parsers.StrictJSONParser"],
    "EXCEPTION_HANDLER": "api.errors.exception_handler",
    "LIST_SERIALIZER_ERRORS_AS_DICT": True,
    "URL_FORMAT_OVERRIDE": None,
}

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Havana"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
CSRF_FAILURE_VIEW = "api.errors.csrf_failure"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
STATIC_URL = "/static/"
STATIC_ROOT = REPO_DIR / ".cache" / "staticfiles"
FRONTEND_INDEX = REPO_DIR / ".cache" / "web" / "index.html"
FRONTEND_ASSET_MANIFEST = REPO_DIR / ".cache" / "web" / "versioned-assets.json"
STATICFILES_DIRS = [("entrepares", REPO_DIR / ".cache" / "web" / "static" / "entrepares")]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = False
WHITENOISE_ALLOW_ALL_ORIGINS = False
WHITENOISE_IMMUTABLE_FILE_TEST = immutable_frontend_file
WHITENOISE_ADD_HEADERS_FUNCTION = frontend_static_headers
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
