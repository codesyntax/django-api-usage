"""Optional DRF integration: scope-based permissions with a shadow mode.

Importing this module requires ``djangorestframework`` to be installed.

The point of the shadow mode is to let a new permission be **deployed and
measured before it is enforced**: with ``API_ENFORCEMENT = "report"`` nothing is
blocked, and the middleware adds an ``X-Api-Would-Deny`` header so you can see
what the permission would have rejected.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission

from .conf import api_settings

REPORT = "report"
WARN = "warn"
ENFORCE = "enforce"


def enforcement_mode(view=None):
    """Resolve the enforcement mode, honouring per-view/per-endpoint overrides."""
    overrides = getattr(settings, "API_ENFORCEMENT_OVERRIDES", {}) or {}
    if view is not None:
        key = getattr(view, "enforcement_key", None) or getattr(view, "basename", None)
        if key and key in overrides:
            return overrides[key]
    return getattr(settings, "API_ENFORCEMENT", REPORT)


def default_role_scopes(user):
    """Scopes granted to a user.

    Uses ``user.get_api_scopes()`` when the project exposes it, otherwise maps
    Django groups named ``api:<scope>`` (e.g. ``api:content:write``).
    """
    getter = getattr(user, "get_api_scopes", None)
    if callable(getter):
        return set(getter())
    return {
        group.name[4:] for group in user.groups.all() if group.name.startswith("api:")
    }


def granted_scopes(request):
    """Scopes granted to the caller: client key scopes, or role-derived scopes."""
    scopes = set()
    api_key = getattr(request, "api_key", None)
    if api_key is not None:
        scopes.update(api_key.scopes.values_list("code", flat=True))
        return scopes
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        scopes.update(api_settings.ROLE_SCOPES_RESOLVER(user))
    return scopes


class HasAPIScope(BasePermission):
    """Require the scopes declared in ``view.required_scopes``.

    Views that declare no scopes are denied (fail closed) once enforcing.
    """

    def has_permission(self, request, view):
        required = set(getattr(view, "required_scopes", ()) or ())
        if required and required <= granted_scopes(request):
            return True
        if enforcement_mode(view) in (REPORT, WARN):
            request._api_usage_would_deny = sorted(required)
            return True
        return False
