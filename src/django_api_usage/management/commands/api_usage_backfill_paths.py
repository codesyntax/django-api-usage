"""Fill in the route path of endpoints recorded before it was captured.

``Endpoint.route_path`` was added in 0.1.3, so endpoints recorded earlier only
have their route *name* (``town-list``). Running this once resolves the name
back to its path (``api/3.0/herriak/``), which is what the admin shows.

    python manage.py api_usage_backfill_paths --dry-run
    python manage.py api_usage_backfill_paths
"""

from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse

from django_api_usage.models import Endpoint


class Command(BaseCommand):
    help = "Resolve the route path of endpoints that do not have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        resolved = unresolved = 0

        for endpoint in Endpoint.objects.filter(route_path="").order_by("pk"):
            path = self.resolve(endpoint.route_name)
            if not path:
                unresolved += 1
                self.stderr.write(
                    f"  could not resolve {endpoint.route_name!r} (left as it is)"
                )
                continue
            resolved += 1
            if not dry_run:
                Endpoint.objects.filter(pk=endpoint.pk).update(route_path=path)

        verb = "would be filled in" if dry_run else "filled in"
        self.stdout.write(
            f"{resolved} route path(s) {verb}; {unresolved} left without a path."
        )

    @staticmethod
    def resolve(route_name):
        """Path for a named route; a route that already is a pattern is reused."""
        if not route_name or route_name == "unknown":
            return ""
        if route_name.startswith("^"):
            # No url name: the captured "name" is the pattern itself.
            return route_name.strip("^$")
        try:
            return reverse(route_name).lstrip("/")
        except NoReverseMatch:
            return ""
