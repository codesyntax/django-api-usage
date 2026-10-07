"""Default resolvers describing a request.

Everything here is overridable from ``API_USAGE`` so the package stays free of
project-specific knowledge. Resolvers must be cheap: they run on every request.
"""

import hashlib

from django.conf import settings as django_settings


def _view_module(match):
    """Best-effort module name of the callable that handled the request."""
    func = getattr(match, "func", None)
    view_class = getattr(func, "cls", None)  # class-based views and DRF viewsets
    if view_class is not None:
        return getattr(view_class, "__module__", "") or ""
    return getattr(func, "__module__", "") or ""


def default_app_label(request):
    """Return a short application label for the resolved view.

    ``tokikom.gida.views`` -> ``gida``, ``myproject.api.rest_views`` -> ``api``.
    Override with ``API_USAGE["APP_LABEL_RESOLVER"]`` when your layout differs.
    """
    match = getattr(request, "resolver_match", None)
    if match is None:
        return "unknown"
    if getattr(match, "app_name", None):
        return match.app_name
    parts = [part for part in _view_module(match).split(".") if part]
    if not parts:
        return "unknown"
    suffixes = {"views", "viewsets", "rest_views", "api"}
    if len(parts) >= 2 and parts[-1] in suffixes:
        return parts[-2]
    return parts[-1]


def default_route_name(request):
    """Return the named URL pattern, never the raw path (cardinality!)."""
    match = getattr(request, "resolver_match", None)
    if match is None:
        return "unknown"
    return (
        getattr(match, "url_name", None) or getattr(match, "route", None) or "unknown"
    )


def default_client_type(request):
    """Classify the caller as ``client``, ``user`` or ``anon``."""
    if getattr(request, "api_client", None) is not None:
        return "client"
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return "user"
    return "anon"


def default_site_id(request):
    """Return ``settings.SITE_ID`` as an int, or ``None`` when not configured."""
    site_id = getattr(django_settings, "SITE_ID", None)
    if site_id is None:
        return None
    try:
        return int(site_id)
    except (TypeError, ValueError):
        return None


def _hash(value, salt):
    return hashlib.sha256("{}:{}".format(salt, value).encode("utf-8")).hexdigest()


def _user_agent_family(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "") or ""
    return user_agent.split(" ")[0][:64]


def default_consumer(request):
    """Return ``(kind, ref_hash, user_agent_family)`` or ``None``.

    Raw identifiers are never stored: only a salted SHA-256 digest. Set
    ``API_USAGE["CONSUMER_SALT"]`` to a secret, rotatable value.
    """
    from .conf import api_settings

    salt = api_settings.CONSUMER_SALT or django_settings.SECRET_KEY
    user_agent_family = _user_agent_family(request)

    api_key = getattr(request, "api_key", None)
    if api_key is not None:
        return ("api_key", _hash(str(api_key.pk), salt), user_agent_family)

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return ("user", _hash(str(user.pk), salt), user_agent_family)

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    if not ip:
        return None
    return ("ip_hash", _hash(ip, salt), user_agent_family)
