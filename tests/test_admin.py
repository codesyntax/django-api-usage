from django.contrib.auth.models import User
from django.urls import reverse

from django_api_usage.models import Endpoint, EndpointStat

from .base import UsageTestCase

CHANGELIST = "admin:django_api_usage_endpointstat_changelist"
FLUSH_URL = "admin:django_api_usage_endpointstat_flush"
CLEAR_URL = "admin:django_api_usage_endpointstat_clear"


class AdminButtonsTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.force_login(self.admin)

    def _make_stat(self, count=1):
        endpoint = Endpoint.objects.create(
            app_label="api", route_name="artikuluak-list", method="GET"
        )
        return EndpointStat.objects.create(
            endpoint=endpoint, date="2026-10-08", count=count
        )

    def test_buttons_are_rendered(self):
        response = self.client.get(reverse(CHANGELIST))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse(FLUSH_URL), content)
        self.assertIn(reverse(CLEAR_URL), content)

    def test_flush_reports_when_nothing_is_buffered(self):
        response = self.client.post(reverse(FLUSH_URL), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in the database")

    def test_flush_moves_buffered_counters_to_the_database(self):
        # A request fills the cache buffer.
        self.client.get("/ping/")
        self.assertFalse(EndpointStat.objects.exists())

        response = self.client.post(reverse(FLUSH_URL), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EndpointStat.objects.filter(endpoint__route_name="ping").exists()
        )

    def test_flush_rejects_get(self):
        response = self.client.get(reverse(FLUSH_URL))

        self.assertRedirects(response, reverse(CHANGELIST))

    def test_clear_asks_for_confirmation_first(self):
        self._make_stat()

        response = self.client.get(reverse(CLEAR_URL))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(EndpointStat.objects.exists())

    def test_clear_deletes_statistics_but_keeps_endpoints(self):
        self._make_stat()

        response = self.client.post(reverse(CLEAR_URL), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EndpointStat.objects.exists())
        self.assertTrue(Endpoint.objects.exists())

    def test_total_sums_the_count_column(self):
        api = Endpoint.objects.create(app_label="api", route_name="a", method="GET")
        gida = Endpoint.objects.create(app_label="gida", route_name="b", method="GET")
        EndpointStat.objects.create(
            endpoint=api, date="2026-10-08", client_type="anon", count=5
        )
        EndpointStat.objects.create(
            endpoint=gida, date="2026-10-08", client_type="user", count=7
        )

        response = self.client.get(reverse(CHANGELIST))

        self.assertEqual(response.context_data["usage_total"], 12)
        self.assertContains(response, "Total calls in the filtered rows")

    def test_total_respects_the_selected_filters(self):
        api = Endpoint.objects.create(app_label="api", route_name="a", method="GET")
        gida = Endpoint.objects.create(app_label="gida", route_name="b", method="GET")
        EndpointStat.objects.create(
            endpoint=api, date="2026-10-08", client_type="anon", count=5
        )
        EndpointStat.objects.create(
            endpoint=gida, date="2026-10-08", client_type="user", count=7
        )

        response = self.client.get(reverse(CHANGELIST), {"client_type": "user"})

        self.assertEqual(response.context_data["usage_total"], 7)

    def test_clear_is_not_available_without_admin_permission(self):
        self._make_stat()
        self.client.force_login(User.objects.create_user("plain", password="x"))

        response = self.client.post(reverse(CLEAR_URL))

        self.assertIn(response.status_code, (302, 403))
        self.assertTrue(EndpointStat.objects.exists())
