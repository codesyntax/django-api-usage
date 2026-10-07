"""Middleware subclasses used by the tests."""

from django_api_usage.middleware import ApiUsageMiddleware


class SubclassedMiddleware(ApiUsageMiddleware):
    """Example of a project narrowing what gets metered."""

    @staticmethod
    def _is_ignored(request):
        return not (request.path or "").startswith("/api/")
