"""Django system checks: catch misconfiguration early."""

from django.conf import settings
from django.core.checks import Warning, register

from .conf import api_settings

W001 = Warning(
    "django-api-usage is enabled but 'django_api_usage.middleware.ApiUsageMiddleware' "
    "is not in MIDDLEWARE; no usage will be recorded.",
    id="api_usage.W001",
)
W002 = Warning(
    "API_USAGE['TRACK_CONSUMERS'] is enabled but API_USAGE['CONSUMER_SALT'] is empty; "
    "SECRET_KEY will be used as the salt. Set an explicit, rotatable salt.",
    id="api_usage.W002",
)
W003 = Warning(
    "API_USAGE['BUFFER_BACKEND'] is 'cache' but the configured cache backend is "
    "DummyCache, which stores nothing: no usage will be recorded. Configure a real "
    "cache or set BUFFER_BACKEND='db'.",
    id="api_usage.W003",
)

DUMMY_CACHE_BACKEND = "django.core.cache.backends.dummy.DummyCache"


def _cache_backend_path():
    """Dotted path of the configured cache backend, or '' if unavailable."""
    from django.core.cache import caches

    try:
        backend = caches[api_settings.CACHE_ALIAS]
    except Exception:  # pragma: no cover - misconfigured CACHES
        return ""
    backend_class = type(backend)
    return f"{backend_class.__module__}.{backend_class.__name__}"


@register()
def api_usage_checks(app_configs, **kwargs):
    errors = []
    if not api_settings.ENABLED:
        return errors

    middleware = list(getattr(settings, "MIDDLEWARE", []))
    if "django_api_usage.middleware.ApiUsageMiddleware" not in middleware:
        errors.append(W001)

    if api_settings.TRACK_CONSUMERS and not api_settings.CONSUMER_SALT:
        errors.append(W002)

    if (
        api_settings.BUFFER_BACKEND == "cache"
        and _cache_backend_path() == DUMMY_CACHE_BACKEND
    ):
        errors.append(W003)

    return errors
