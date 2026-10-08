"""Tests for the "export selected rows to CSV" admin action."""

import csv
import io

from django.contrib.auth.models import User
from django.urls import reverse

from django_api_usage.models import Consumer, Endpoint, EndpointStat

from .base import UsageTestCase

ENDPOINT_CHANGELIST = "admin:django_api_usage_endpoint_changelist"
STAT_CHANGELIST = "admin:django_api_usage_endpointstat_changelist"
CONSUMER_CHANGELIST = "admin:django_api_usage_consumer_changelist"

BOM = b"\xef\xbb\xbf"


class CsvExportTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)

    # -- helpers ------------------------------------------------------------

    def export(self, changelist, objects, action="export_as_csv"):
        return self.client.post(
            reverse(changelist),
            {
                "action": action,
                "select_across": "0",
                "index": "0",
                "_selected_action": [str(obj.pk) for obj in objects],
            },
        )

    def rows(self, response):
        """Return the CSV as a list of rows (BOM stripped)."""
        content = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(content)))

    def make_endpoint(self, route_path="api/3.0/herriak/", app_label="api"):
        return Endpoint.objects.create(
            app_label=app_label,
            route_path=route_path,
            route_name="town-list",
            method="GET",
        )

    def make_stat(self, endpoint, count=1, client_type="anon"):
        return EndpointStat.objects.create(
            endpoint=endpoint,
            date="2026-10-08",
            client_type=client_type,
            status_class="2xx",
            count=count,
        )

    def assert_csv_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".csv", response["Content-Disposition"])
        # The BOM makes Excel detect UTF-8.
        self.assertTrue(response.content.startswith(BOM))

    # -- action availability ------------------------------------------------

    def test_action_is_offered_in_the_changelist(self):
        endpoint = self.make_endpoint()
        self.make_stat(endpoint)

        response = self.client.get(reverse(STAT_CHANGELIST))

        self.assertContains(response, "Export selected rows to CSV")
        self.assertContains(response, 'value="export_as_csv"')

    def test_delete_selected_is_still_available(self):
        self.make_endpoint()

        changelist = self.client.get(reverse(ENDPOINT_CHANGELIST))

        self.assertContains(changelist, "delete_selected")

    # -- stats export -------------------------------------------------------

    def test_stats_export_header_is_stable(self):
        endpoint = self.make_endpoint()
        stat = self.make_stat(endpoint)

        response = self.export(STAT_CHANGELIST, [stat])

        self.assert_csv_response(response)
        self.assertEqual(
            self.rows(response)[0],
            [
                "date",
                "app_label",
                "route_path",
                "route_name",
                "method",
                "site_id",
                "client_type",
                "client_app",
                "status_class",
                "count",
            ],
        )

    def test_stats_export_flattens_the_endpoint(self):
        endpoint = self.make_endpoint(route_path="^api/3.0/herriak/$")
        stat = self.make_stat(endpoint, count=7)

        response = self.export(STAT_CHANGELIST, [stat])

        body = self.rows(response)[1]
        self.assertEqual(body[0], "2026-10-08")
        self.assertEqual(body[1], "api")
        self.assertEqual(body[2], "^api/3.0/herriak/$")
        self.assertEqual(body[3], "town-list")
        self.assertEqual(body[4], "GET")
        self.assertEqual(body[6], "anon")
        self.assertEqual(body[7], "")
        self.assertEqual(body[8], "2xx")
        self.assertEqual(body[9], "7")

    def test_stats_export_only_includes_the_selected_rows(self):
        endpoint = self.make_endpoint()
        selected = self.make_stat(endpoint, count=1)
        self.make_stat(endpoint, count=99, client_type="user")

        response = self.export(STAT_CHANGELIST, [selected])

        rows = self.rows(response)
        self.assertEqual(len(rows), 2)  # header + one row
        self.assertEqual(rows[1][9], "1")

    def test_stats_export_filename_contains_the_date(self):
        endpoint = self.make_endpoint()
        stat = self.make_stat(endpoint)

        response = self.export(STAT_CHANGELIST, [stat])

        self.assertIn('filename="django-api-usage-', response["Content-Disposition"])

    # -- endpoints and consumers export -------------------------------------

    def test_endpoints_export(self):
        endpoint = self.make_endpoint()
        Endpoint.objects.filter(pk=endpoint.pk).update(
            deprecated=True, replacement="api/4.0/herriak/"
        )

        response = self.export(ENDPOINT_CHANGELIST, [endpoint])

        self.assert_csv_response(response)
        rows = self.rows(response)
        self.assertIn("deprecated", rows[0])
        self.assertIn("replacement", rows[0])
        self.assertIn("True", rows[1])
        self.assertIn("api/4.0/herriak/", rows[1])

    def test_consumers_export(self):
        consumer = Consumer.objects.create(
            kind="ip_hash",
            ref_hash="a" * 64,
            user_agent_family="firefox",
            request_count=12,
        )

        response = self.export(CONSUMER_CHANGELIST, [consumer])

        self.assert_csv_response(response)
        rows = self.rows(response)
        self.assertEqual(rows[0][0], "kind")
        self.assertEqual(rows[0][1], "ref_hash")
        self.assertEqual(rows[1][0], "ip_hash")
        self.assertEqual(rows[1][1], "a" * 64)

    # -- edge cases ---------------------------------------------------------

    def test_export_without_selection_is_not_a_csv(self):
        """Django warns and redirects instead of downloading an empty file."""
        response = self.client.post(
            reverse(STAT_CHANGELIST),
            {"action": "export_as_csv", "select_across": "0", "index": "0"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.get("Content-Type"), "text/csv; charset=utf-8")

    def test_export_all_matching_rows_with_select_across(self):
        """One checked row + "select all" exports every row matching the filters."""
        endpoint = self.make_endpoint()
        first = self.make_stat(endpoint, count=1)
        self.make_stat(endpoint, count=2, client_type="user")

        response = self.client.post(
            reverse(STAT_CHANGELIST),
            {
                "action": "export_as_csv",
                "select_across": "1",
                "index": "0",
                "_selected_action": [str(first.pk)],
            },
        )

        self.assert_csv_response(response)
        self.assertEqual(len(self.rows(response)), 3)  # header + two rows
