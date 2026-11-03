"""Identificadores técnicos; conocer uno no concede acceso a su recurso."""

from uuid import UUID, uuid4


def new_id() -> UUID:
    """Genera un UUID v4, independiente de las credenciales y tokens de verificación."""
    return uuid4()
