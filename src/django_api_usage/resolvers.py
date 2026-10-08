"""Default resolvers describing a request.

Everything here is overridable from ``API_USAGE`` so the package stays free of
project-specific knowledge. Resolvers must be cheap: they run on every request.
"""

import hashlib
import ipaddress
import logging
import time
from urllib.parse import urlsplit

from django.conf import settings as django_settings

logger = logging.getLogger("django_api_usage")


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


def default_route_path(request):
    """Return the URL pattern that matched, e.g. ``api/3.0/herriak/``.

    Path *patterns* (never the raw path) keep cardinality bounded. This is what
    people search for in the admin, so it is stored next to ``route_name``.
    """
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    return getattr(match, "route", "") or ""


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
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


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


# -- client application attribution -----------------------------------------

#: Safety net for processes that did not see the signal (see ``apps.py``).
CLIENT_APP_RULES_TTL = 60
_rules_cache = {"loaded_at": 0.0, "rules": None}


def reset_client_app_cache(**kwargs):
    """Forget the cached :class:`~django_api_usage.models.ClientApp` rules."""
    _rules_cache["rules"] = None
    _rules_cache["loaded_at"] = 0.0


def _load_client_app_rules():
    from .models import ClientApp

    rules = {"by_user": {}, "hosts": [], "networks": [], "patterns": []}
    apps = ClientApp.objects.filter(is_active=True).prefetch_related("accounts")
    for app in apps:  # ordered by priority, then slug
        for user_id in app.accounts.values_list("pk", flat=True):
            rules["by_user"].setdefault(user_id, app.slug)
        rules["hosts"].extend((host.lower(), app.slug) for host in app.domain_list())
        for cidr in app.network_list():
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                logger.warning(
                    "django-api-usage: ignoring invalid network %r on %s", cidr, app
                )
                continue
            rules["networks"].append((network, app.slug))
        rules["patterns"].extend(
            (pattern, app.slug) for pattern in app.user_agent_list()
        )
    return rules


def _client_app_rules():
    now = time.monotonic()
    if (
        _rules_cache["rules"] is None
        or now - _rules_cache["loaded_at"] > CLIENT_APP_RULES_TTL
    ):
        _rules_cache["rules"] = _load_client_app_rules()
        _rules_cache["loaded_at"] = now
    return _rules_cache["rules"]


def _request_host(request):
    """Host of the ``Origin`` (or ``Referer``) header, lowercased."""
    for header in ("HTTP_ORIGIN", "HTTP_REFERER"):
        value = request.META.get(header)
        if value:
            host = urlsplit(value).hostname
            if host:
                return host.lower()
    return ""


def client_ip(request):
    """Client address, honouring the first ``X-Forwarded-For`` entry."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def client_app_from_rules(request):
    """Attribute the caller to a :class:`ClientApp`, or return ``""``.

    The rules live in the database and are editable from the admin, so a new
    consumer can be recognised without a deploy. Monitored order: the caller's
    account (a dedicated token), then the request host, then the client network,
    then the user agent. ``ClientApp.priority`` decides the order between apps.
    """
    rules = _client_app_rules()

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        slug = rules["by_user"].get(user.pk)
        if slug:
            return slug

    host = _request_host(request)
    if host:
        for pattern, slug in rules["hosts"]:
            if host == pattern or host.endswith("." + pattern):
                return slug

    address = _as_address(client_ip(request))
    if address is not None:
        for network, slug in rules["networks"]:
            if address.version == network.version and address in network:
                return slug

    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    if user_agent:
        for pattern, slug in rules["patterns"]:
            if pattern in user_agent:
                return slug
    return ""


def _as_address(value):
    if not value:
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None
