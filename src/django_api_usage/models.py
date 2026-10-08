"""Data model.

Three layers live here on purpose:

* **Usage metering** (:class:`Endpoint`, :class:`EndpointStat`) is the neutral
  core: how much is each endpoint of each app used, and by which client
  application (:class:`ClientApp`).
* **Client attribution** (:class:`ClientApp`) is editable data, so new consumers
  can be recognised from the admin without a deploy.
* **Deprecation lifecycle** (the extra fields on :class:`Endpoint`) is the
  optional layer built on top of the same data.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _lines(value):
    """Split a textarea into non-empty, stripped lines."""
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class Endpoint(models.Model):
    """One distinct (site, app, route, method) combination that was called."""

    # Plain integer instead of a FK to sites.Site: keeps the package usable in
    # projects without django.contrib.sites.
    site_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    app_label = models.CharField(max_length=64, db_index=True)
    route_name = models.CharField(max_length=160)
    # URL pattern that matched (e.g. "api/3.0/herriak/"). Informational: the
    # endpoint identity stays (site, app, route_name, method). Makes the admin
    # searchable by path, which is how people actually refer to endpoints.
    route_path = models.CharField(max_length=200, blank=True)
    method = models.CharField(max_length=8)

    # Deprecation lifecycle (optional layer).
    deprecated = models.BooleanField(default=False)
    sunset_date = models.DateField(null=True, blank=True)
    replacement = models.CharField(max_length=160, blank=True)
    owner = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("site_id", "app_label", "route_name", "method")
        ordering = ("app_label", "route_name", "method")

    def __str__(self):
        return f"{self.method} {self.route_path or self.route_name} ({self.app_label})"

    @property
    def is_sunset(self):
        """True when the sunset date has been reached."""
        return bool(self.sunset_date and self.sunset_date <= timezone.localdate())

    @property
    def days_until_sunset(self):
        if not self.sunset_date:
            return None
        return (self.sunset_date - timezone.localdate()).days


class ClientApp(models.Model):
    """An application that consumes the API (mobile app, ERP, partner, ...).

    Editable on purpose: the mapping is data, not code. A blank ``slug``-less
    request is attributed to no app at all, so the rules can grow without a
    deploy.

    Resolution order is: authenticated account, request host, client network,
    then user agent. ``priority`` breaks ties (lower wins).
    """

    slug = models.SlugField(
        max_length=64,
        unique=True,
        help_text=_("Short, stable label stored in the counters (e.g. 'mugikorra')."),
    )
    name = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(
        default=100, help_text=_("Lower wins when several apps could match.")
    )
    domains = models.TextField(
        blank=True,
        help_text=_("One host per line; matched against the Origin/Referer host."),
    )
    ip_networks = models.TextField(
        blank=True, help_text=_("One CIDR per line, e.g. 10.0.0.0/8.")
    )
    user_agent_patterns = models.TextField(
        blank=True,
        help_text=_("One substring per line, matched case-insensitively."),
    )

    class Meta:
        verbose_name = _("Client application")
        verbose_name_plural = _("Client applications")
        ordering = ("priority", "slug")

    def __str__(self):
        return self.name or self.slug

    def domain_list(self):
        return _lines(self.domains)

    def network_list(self):
        return _lines(self.ip_networks)

    def user_agent_list(self):
        return [pattern.lower() for pattern in _lines(self.user_agent_patterns)]


class ClientAppAccount(models.Model):
    """Assigns one account (and therefore its DRF token) to an application.

    One row per account, indexed, instead of a many-to-many holding the account
    list of every application: the resolver does a single point lookup and
    nothing has to be loaded into memory. Only real integrations belong here
    (an ERP, a partner); ordinary readers of the mobile apps are matched by
    their user agent, not by account.
    """

    client_app = models.ForeignKey(
        ClientApp, on_delete=models.CASCADE, related_name="accounts"
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_usage_client_app",
        verbose_name=_("Account"),
        help_text=_("One application per account, so the token is unambiguous."),
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("Client application account")
        verbose_name_plural = _("Client application accounts")
        ordering = ("client_app", "user")

    def __str__(self):
        return f"{self.client_app} ← {self.user}"


class EndpointStat(models.Model):
    """Aggregated counter per endpoint, day, client and status class."""

    endpoint = models.ForeignKey(
        Endpoint, on_delete=models.CASCADE, related_name="stats"
    )
    date = models.DateField(db_index=True)
    client_type = models.CharField(max_length=16, default="anon")
    #: ``ClientApp.slug``; blank when the caller could not be attributed.
    client_app = models.CharField(max_length=64, blank=True)
    status_class = models.CharField(max_length=4, default="2xx")
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (
            "endpoint",
            "date",
            "client_type",
            "client_app",
            "status_class",
        )
        ordering = ("-date",)
        indexes = [models.Index(fields=["date", "endpoint"])]

    def __str__(self):
        return f"{self.date} {self.endpoint} {self.client_type} {self.count}"


class Consumer(models.Model):
    """An observed caller, identified only by a salted hash. Opt-in."""

    KIND_CHOICES = (
        ("api_key", "API key"),
        ("user", "User"),
        ("ip_hash", "IP hash"),
    )

    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    ref_hash = models.CharField(max_length=64, db_index=True)
    user_agent_family = models.CharField(max_length=64, blank=True)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    request_count = models.PositiveIntegerField(default=0)
    # Manually maintained: who to contact before deprecating something.
    contact = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("kind", "ref_hash")
        ordering = ("-last_seen",)

    def __str__(self):
        return f"{self.kind} {self.ref_hash[:12]}"
