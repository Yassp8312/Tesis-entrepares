"""Comprobaciones locales sin .env; no sirve como configuración WSGI."""

from .test import *  # noqa: F403

# El flujo prepara Vue antes de coleccionar los estáticos con estos ajustes.
STATICFILES_DIRS = [("entrepares", REPO_DIR / ".cache" / "web" / "static" / "entrepares")]  # noqa: F405
