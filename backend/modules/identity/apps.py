from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "modules.identity"
    label = "identity"
    verbose_name = "Identidad"

    def ready(self):
        from . import checks  # noqa: F401
