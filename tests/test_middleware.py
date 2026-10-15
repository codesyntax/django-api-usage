from django.test import override_settings

from django_api_usage.buffers import flush
from django_api_usage.conf import api_settings
from django_api_usage.models import Consumer, Endpoint, EndpointStat

from .base import UsageTestCase


class MiddlewareTest(UsageTestCase):
    def test_records_an_aggregated_hit(self):
        response = self.client.get("/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(flush(), 1)

        stat = EndpointStat.objects.get()
        self.assertEqual(stat.count, 1)
        self.assertEqual(stat.status_class, "2xx")
        self.assertEqual(stat.client_type, "anon")
        self.assertEqual(stat.endpoint.route_name, "ping")
        self.assertEqual(stat.endpoint.route_path, "ping/")
        self.assertEqual(stat.endpoint.method, "GET")

    def test_aggregates_repeated_hits(self):
        self.client.get("/ping/")
        self.client.get("/ping/")
        flush()

        self.assertEqual(Endpoint.objects.count(), 1)
        self.assertEqual(EndpointStat.objects.get().count, 2)

    def test_error_responses_are_classified(self):
        self.client.get("/boom/")
        flush()
        self.assertEqual(EndpointStat.objects.get().status_class, "5xx")


class ConsumerTrackingTest(UsageTestCase):
    def test_anonymous_consumer_is_hashed(self):
        self.client.get("/ping/")
        consumer = Consumer.objects.get()
        self.assertEqual(consumer.kind, "ip_hash")
        self.assertEqual(len(consumer.ref_hash), 64)
        self.assertEqual(consumer.request_count, 1)

    def test_raw_ip_is_not_stored(self):
        self.client.get("/ping/", REMOTE_ADDR="203.0.113.9")
        consumer = Consumer.objects.get()
        self.assertNotIn("203.0.113.9", consumer.ref_hash)


class WouldDenyTrackingTest(UsageTestCase):
    """Shadow-mode denies can be counted as a synthetic ``403*`` status class."""

    def test_shadow_denies_are_not_counted_by_default(self):
        self.client.get("/shadow/")
        flush()

        self.assertEqual(EndpointStat.objects.count(), 1)
        self.assertEqual(EndpointStat.objects.get().status_class, "2xx")

    def test_shadow_denies_are_counted_when_enabled(self):
        current = dict(api_settings.user_settings)
        self.addCleanup(api_settings.reload)

        with override_settings(API_USAGE={**current, "TRACK_WOULD_DENY": True}):
            api_settings.reload()
            self.client.get("/shadow/")
            flush()

        self.assertEqual(EndpointStat.objects.get(status_class="403*").count, 1)
        # The real hit is still counted, with its own status class.
        self.assertEqual(EndpointStat.objects.get(status_class="2xx").count, 1)
