from datetime import timedelta

from django.utils import timezone

from django_api_usage.models import Endpoint

from .base import UsageTestCase


class EndpointModelTest(UsageTestCase):
    def test_future_sunset_date(self):
        endpoint = Endpoint.objects.create(
            app_label="api",
            route_name="ping",
            method="GET",
            sunset_date=timezone.localdate() + timedelta(days=5),
        )
        self.assertFalse(endpoint.is_sunset)
        self.assertEqual(endpoint.days_until_sunset, 5)

    def test_past_sunset_date(self):
        endpoint = Endpoint.objects.create(
            app_label="api",
            route_name="old",
            method="GET",
            sunset_date=timezone.localdate() - timedelta(days=1),
        )
        self.assertTrue(endpoint.is_sunset)

    def test_no_sunset_date(self):
        endpoint = Endpoint.objects.create(
            app_label="api", route_name="plain", method="GET"
        )
        self.assertFalse(endpoint.is_sunset)
        self.assertIsNone(endpoint.days_until_sunset)
