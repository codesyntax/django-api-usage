from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from django_api_usage.maintenance import prune
from django_api_usage.models import Endpoint, EndpointStat

from .base import UsageTestCase


class ReportCommandTest(UsageTestCase):
    def test_report_lists_usage(self):
        self.client.get("/ping/")
        from django_api_usage.buffers import flush

        flush()

        out = StringIO()
        call_command("api_usage_report", "--days", "30", stdout=out)
        self.assertIn("ping", out.getvalue())

    def test_sunset_candidates_excludes_used_endpoints(self):
        self.client.get("/ping/")
        from django_api_usage.buffers import flush

        flush()

        out = StringIO()
        call_command("api_usage_report", "--sunset-candidates", stdout=out)
        self.assertNotIn("ping", out.getvalue())
        self.assertIn("Total: 0", out.getvalue())


class FlushCommandTest(UsageTestCase):
    def test_flush_writes_buffered_counters(self):
        self.client.get("/ping/")
        out = StringIO()
        call_command("api_usage_flush", stdout=out)
        self.assertIn("Flushed 1", out.getvalue())
        self.assertTrue(EndpointStat.objects.exists())

    def test_prune_removes_rows_outside_retention(self):
        endpoint = Endpoint.objects.create(
            app_label="api", route_name="x", method="GET"
        )
        EndpointStat.objects.create(
            endpoint=endpoint,
            date=timezone.localdate() - timedelta(days=200),
            count=5,
        )
        self.assertEqual(prune(), 1)
        self.assertFalse(EndpointStat.objects.exists())
