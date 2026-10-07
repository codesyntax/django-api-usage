"""Deprecation lifecycle helpers built on top of the usage counters."""

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import Endpoint, EndpointStat


def usage(period_days=90, site_id=None):
    """Return ``[(endpoint, calls), ...]`` for every known endpoint."""
    since = timezone.localdate() - timedelta(days=period_days)
    endpoints = Endpoint.objects.all()
    if site_id is not None:
        endpoints = endpoints.filter(site_id=site_id)
    totals = (
        EndpointStat.objects.filter(date__gte=since)
        .values("endpoint_id")
        .annotate(total=Sum("count"))
    )
    by_id = {row["endpoint_id"]: row["total"] for row in totals}
    return [(endpoint, by_id.get(endpoint.pk, 0)) for endpoint in endpoints]


def in_use(period_days=90, site_id=None):
    """Endpoints with traffic in the period, most used first."""
    rows = [(ep, total) for ep, total in usage(period_days, site_id) if total > 0]
    return sorted(rows, key=lambda row: row[1], reverse=True)


def candidates_for_deprecation(period_days=90, site_id=None):
    """Endpoints with no traffic in the period: the safe ones to deprecate."""
    return [ep for ep, total in usage(period_days, site_id) if total == 0]
