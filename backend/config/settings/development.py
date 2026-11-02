"""Desarrollo local sobre PostgreSQL, sin alterar la configuración de producción."""

from config.environment import env_bool

from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", True)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
