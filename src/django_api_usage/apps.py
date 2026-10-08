from django.apps import AppConfig


class DjangoApiUsageConfig(AppConfig):
    name = "django_api_usage"
    verbose_name = "Django API usage"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Register system checks (middleware installed, consumer salt, ...).
        from . import checks  # noqa: F401

        self._connect_client_app_signals()

    def _connect_client_app_signals(self):
        """Drop the cached ClientApp rules as soon as the table changes."""
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from .models import ClientApp
        from .resolvers import reset_client_app_cache

        post_save.connect(
            reset_client_app_cache, sender=ClientApp, dispatch_uid="api_usage_app_save"
        )
        post_delete.connect(
            reset_client_app_cache,
            sender=ClientApp,
            dispatch_uid="api_usage_app_delete",
        )
        m2m_changed.connect(
            reset_client_app_cache,
            sender=ClientApp.accounts.through,
            dispatch_uid="api_usage_app_accounts",
        )
