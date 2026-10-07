"""Configuration for django-api-usage.

Every option is read from the ``API_USAGE`` dictionary in Django settings::

    API_USAGE = {
        "ENABLED": True,
        "TRACK_CONSUMERS": False,
    }

Resolver options accept either a dotted path to a callable or the callable
itself. Nothing in this module depends on the host project.
"""

from django.utils.module_loading import import_string

DEFAULTS = {
    # Master switch: when False the middleware becomes a no-op.
    "ENABLED": True,
    # Metering must never break a request.
    "FAIL_OPEN": True,
    # "cache" buffers counters in the cache and writes them in batches;
    # "db" writes one aggregate update per request (simpler, slower).
    "BUFFER_BACKEND": "cache",
    "CACHE_ALIAS": "default",
    "CACHE_PREFIX": "api_usage",
    # Raw per-day aggregates older than this are pruned. 0 keeps them forever.
    "RETENTION_DAYS": 90,
    # Opt-in consumer attribution. Only salted hashes are stored; see the docs.
    "TRACK_CONSUMERS": False,
    # Salt used to hash consumer identifiers. Keep it secret and rotatable.
    "CONSUMER_SALT": "",
    # Resolvers (dotted path or callable).
    "APP_LABEL_RESOLVER": "django_api_usage.resolvers.default_app_label",
    "ROUTE_NAME_RESOLVER": "django_api_usage.resolvers.default_route_name",
    "CLIENT_TYPE_RESOLVER": "django_api_usage.resolvers.default_client_type",
    "SITE_RESOLVER": "django_api_usage.resolvers.default_site_id",
    "CONSUMER_RESOLVER": "django_api_usage.resolvers.default_consumer",
    "ROLE_SCOPES_RESOLVER": "django_api_usage.drf.default_role_scopes",
    # Regexes matched against request.path; matching requests are not recorded.
    "IGNORE_PATHS": (
        r"^/static/",
        r"^/media/",
        r"^/favicon\.ico$",
    ),
}


class ApiUsageSettings:
    """Lazy accessor over ``settings.API_USAGE`` with sane defaults."""

    def __init__(self, user_settings=None):
        self._user = user_settings
        self._resolved = {}

    @property
    def user_settings(self):
        if self._user is None:
            from django.conf import settings as django_settings

            self._user = getattr(django_settings, "API_USAGE", {}) or {}
        return self._user

    def __getattr__(self, attr):
        if attr not in DEFAULTS:
            raise AttributeError("Invalid API_USAGE setting: '%s'" % attr)
        if attr in self._resolved:
            return self._resolved[attr]
        value = self.user_settings.get(attr, DEFAULTS[attr])
        if attr.endswith("_RESOLVER"):
            if isinstance(value, str):
                value = import_string(value)
            self._resolved[attr] = value
        return value

    def reload(self):
        """Forget cached settings and resolved callables (used in tests)."""
        self._user = None
        self._resolved = {}


api_settings = ApiUsageSettings()
