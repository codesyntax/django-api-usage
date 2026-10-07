from django.apps import AppConfig


class DjangoApiUsageConfig(AppConfig):
    name = "django_api_usage"
    verbose_name = "Django API usage"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Register system checks (middleware installed, consumer salt, ...).
        from . import checks  # noqa: F401
