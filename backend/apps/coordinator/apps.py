from django.apps import AppConfig


class CoordinatorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.coordinator"
    verbose_name = "Practice Manager AI"

    def ready(self):
        from . import signals  # noqa: F401
