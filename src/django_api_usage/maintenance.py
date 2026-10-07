"""Maintenance helpers (retention/pruning)."""

from datetime import timedelta

from django.utils import timezone

from .conf import api_settings
from .models import EndpointStat


def prune(retention_days=None):
    """Delete raw counters older than the retention window.

    Returns the number of deleted rows. ``RETENTION_DAYS = 0`` disables pruning.
    """
    days = api_settings.RETENTION_DAYS if retention_days is None else retention_days
    if not days:
        return 0
    cutoff = timezone.localdate() - timedelta(days=days)
    deleted, _ = EndpointStat.objects.filter(date__lt=cutoff).delete()
    return deleted
