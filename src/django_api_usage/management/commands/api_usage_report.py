"""Report API usage per endpoint and per application.

This is the command that feeds a deprecation decision:

    python manage.py api_usage_report --days 90
    python manage.py api_usage_report --days 90 --sunset-candidates
    python manage.py api_usage_report --app gida
"""

from django.core.management.base import BaseCommand

from django_api_usage.deprecation import candidates_for_deprecation, in_use


class Command(BaseCommand):
    help = "Report API usage per endpoint and app, to support deprecation decisions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Look-back window in days (default: 90).",
        )
        parser.add_argument(
            "--app", dest="app_label", default=None, help="Filter by app."
        )
        parser.add_argument("--site", type=int, default=None, help="Filter by site id.")
        parser.add_argument(
            "--sunset-candidates",
            action="store_true",
            help="List endpoints with no traffic in the window instead of usage.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        site_id = options["site"]
        app_label = options["app_label"]

        if options["sunset_candidates"]:
            endpoints = candidates_for_deprecation(days, site_id)
            if app_label:
                endpoints = [ep for ep in endpoints if ep.app_label == app_label]
            self.stdout.write(
                "Endpoints without traffic in the last {} day(s):".format(days)
            )
            for endpoint in endpoints:
                self.stdout.write(
                    "  {} {} ({})".format(
                        endpoint.method, endpoint.route_name, endpoint.app_label
                    )
                )
            self.stdout.write("Total: {}".format(len(endpoints)))
            return

        rows = in_use(days, site_id)
        if app_label:
            rows = [(ep, total) for ep, total in rows if ep.app_label == app_label]
        self.stdout.write("{:<12} {:<40} {:>10}".format("APP", "ENDPOINT", "CALLS"))
        for endpoint, total in rows:
            self.stdout.write(
                "{:<12} {:<40} {:>10}".format(
                    endpoint.app_label, endpoint.route_name, total
                )
            )
        self.stdout.write("Endpoints with traffic: {}".format(len(rows)))
