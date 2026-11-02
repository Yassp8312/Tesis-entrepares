"""Adaptación de las credenciales de correo a la autenticación técnica de Django."""

from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Conserva comprobaciones y endurecimiento de ModelBackend."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username if username is not None else kwargs.pop("email", None)
        if not isinstance(email, str):
            return None
        return super().authenticate(request, username=email.strip(), password=password, **kwargs)

    async def aauthenticate(self, request, username=None, password=None, **kwargs):
        email = username if username is not None else kwargs.pop("email", None)
        if not isinstance(email, str):
            return None
        return await super().aauthenticate(
            request, username=email.strip(), password=password, **kwargs
        )
