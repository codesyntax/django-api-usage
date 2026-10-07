"""Flush buffered counters and apply the retention window.

Run from cron or a Celery beat schedule:

    python manage.py api_usage_flush
"""

from django.core.management.base import BaseCommand

from django_api_usage.buffers import flush
from django_api_usage.maintenance import prune


class Command(BaseCommand):
    help = "Move buffered counters to the database and prune old rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-prune", action="store_true", help="Skip the retention/pruning step."
        )

    def handle(self, *args, **options):
        written = flush()
        self.stdout.write(f"Flushed {written} counter bucket(s).")
        if not options["no_prune"]:
            deleted = prune()
            self.stdout.write(f"Pruned {deleted} old stat row(s).")
