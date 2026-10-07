"""Optional Celery tasks. Requires the ``celery`` extra."""

from .buffers import flush
from .maintenance import prune

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is an optional dependency
    shared_task = None


if shared_task is not None:

    @shared_task
    def flush_api_usage():
        """Move buffered counters to the database."""
        return flush()

    @shared_task
    def prune_api_usage():
        """Apply the retention window to raw counters."""
        return prune()
