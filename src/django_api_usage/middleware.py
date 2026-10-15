"""Fail-open middleware that meters every Django view, DRF or not."""

import logging
import re

from .buffers import record_hit
from .conf import api_settings

logger = logging.getLogger("django_api_usage")

#: Synthetic status class for requests that shadow mode would have denied.
WOULD_DENY_STATUS_CLASS = "403*"


class ApiUsageMiddleware:
    """Record one aggregated hit per request and expose the shadow-mode header.

    Placed anywhere in ``MIDDLEWARE``; it only needs the final response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if api_settings.ENABLED:
            self._record(request, response)
            self._add_shadow_header(request, response)
        return response

    def _record(self, request, response):
        try:
            if self._is_ignored(request):
                return
            dimensions = {
                "site_id": api_settings.SITE_RESOLVER(request),
                "app_label": api_settings.APP_LABEL_RESOLVER(request),
                "route_name": api_settings.ROUTE_NAME_RESOLVER(request),
                "route_path": api_settings.ROUTE_PATH_RESOLVER(request),
                "method": request.method,
                "client_type": api_settings.CLIENT_TYPE_RESOLVER(request),
                "client_app": api_settings.CLIENT_APP_RESOLVER(request),
            }
            consumer = None
            if api_settings.TRACK_CONSUMERS:
                consumer = api_settings.CONSUMER_RESOLVER(request)
            record_hit(dimensions, response.status_code, consumer)
            self._record_would_deny(request, dimensions, consumer)
        except Exception:
            logger.exception("django-api-usage: could not record request")
            if not api_settings.FAIL_OPEN:
                raise

    @staticmethod
    def _record_would_deny(request, dimensions, consumer):
        """Count a shadow-mode deny as a synthetic ``403*`` hit (opt-in).

        ``request._api_usage_would_deny`` is set by the permission classes
        (:class:`django_api_usage.drf.HasAPIScope` and friends) when enforcement is
        off; the same hook feeds ``X-Api-Would-Deny``.
        """
        if not api_settings.TRACK_WOULD_DENY:
            return
        if getattr(request, "_api_usage_would_deny", None):
            record_hit(dimensions, consumer=consumer, as_class=WOULD_DENY_STATUS_CLASS)

    @staticmethod
    def _add_shadow_header(request, response):
        would_deny = getattr(request, "_api_usage_would_deny", None)
        if would_deny:
            response["X-Api-Would-Deny"] = ",".join(sorted(would_deny))

    @staticmethod
    def _is_ignored(request):
        path = request.path or ""
        for pattern in api_settings.IGNORE_PATHS:
            if re.search(pattern, path):
                return True
        return False
