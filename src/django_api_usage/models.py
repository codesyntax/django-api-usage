"""Data model.

Two layers live here on purpose:

* **Usage metering** (:class:`Endpoint`, :class:`EndpointStat`) is the neutral
  core: how much is each endpoint of each app used.
* **Deprecation lifecycle** (the extra fields on :class:`Endpoint`) is the
  optional layer built on top of the same data.
"""

from django.db import models
from django.utils import timezone


class Endpoint(models.Model):
    """One distinct (site, app, route, method) combination that was called."""

    # Plain integer instead of a FK to sites.Site: keeps the package usable in
    # projects without django.contrib.sites.
    site_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    app_label = models.CharField(max_length=64, db_index=True)
    route_name = models.CharField(max_length=160)
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
        return "{} {} ({})".format(self.method, self.route_name, self.app_label)

    @property
    def is_sunset(self):
        """True when the sunset date has been reached."""
        return bool(self.sunset_date and self.sunset_date <= timezone.localdate())

    @property
    def days_until_sunset(self):
        if not self.sunset_date:
            return None
        return (self.sunset_date - timezone.localdate()).days


class EndpointStat(models.Model):
    """Aggregated counter per endpoint, day, client type and status class."""

    endpoint = models.ForeignKey(
        Endpoint, on_delete=models.CASCADE, related_name="stats"
    )
    date = models.DateField(db_index=True)
    client_type = models.CharField(max_length=16, default="anon")
    status_class = models.CharField(max_length=4, default="2xx")
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("endpoint", "date", "client_type", "status_class")
        ordering = ("-date",)
        indexes = [models.Index(fields=["date", "endpoint"])]

    def __str__(self):
        return "{} {} {} {}".format(
            self.date, self.endpoint, self.client_type, self.count
        )


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
        return "{} {}".format(self.kind, self.ref_hash[:12])
