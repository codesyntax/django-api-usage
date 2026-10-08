"""Tests for the api_usage_backfill_paths command."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from django_api_usage.models import Endpoint


class BackfillPathsTest(TestCase):
    def make(self, route_name, route_path=""):
        return Endpoint.objects.create(
            app_label="api",
            route_name=route_name,
            route_path=route_path,
            method="GET",
        )

    def run_command(self, *args):
        out, err = StringIO(), StringIO()
        call_command("api_usage_backfill_paths", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_a_named_route_is_resolved_to_its_path(self):
        endpoint = self.make("ping")

        self.run_command()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.route_path, "ping/")

    def test_a_route_without_a_name_keeps_its_pattern(self):
        endpoint = self.make("^api/3.0/agenda/")

        self.run_command()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.route_path, "api/3.0/agenda/")

    def test_an_unresolvable_route_is_left_alone_and_reported(self):
        endpoint = self.make("artikuluak-detail")

        out, err = self.run_command()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.route_path, "")
        self.assertIn("could not resolve", err)
        self.assertIn("0 route path(s) filled in", out)

    def test_dry_run_does_not_write(self):
        endpoint = self.make("ping")

        out, _ = self.run_command("--dry-run")

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.route_path, "")
        self.assertIn("would be filled in", out)

    def test_endpoints_that_already_have_a_path_are_untouched(self):
        endpoint = self.make("ping", route_path="api/3.0/ping/")

        self.run_command()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.route_path, "api/3.0/ping/")
