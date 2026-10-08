"""Tests for the Application / Method changelist filters."""

import re

from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import translation

from django_api_usage.admin import MethodListFilter
from django_api_usage.models import Endpoint, EndpointStat

from .base import UsageTestCase

ENDPOINT_CHANGELIST = "admin:django_api_usage_endpoint_changelist"
STAT_CHANGELIST = "admin:django_api_usage_endpointstat_changelist"


class FilterTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)

        self.get_endpoint = Endpoint.objects.create(
            app_label="api",
            route_path="api/3.0/artikuluak/",
            route_name="artikuluak-list",
            method="GET",
        )
        self.post_endpoint = Endpoint.objects.create(
            app_label="api",
            route_path="api/3.0/artikuluak/",
            route_name="artikuluak-create",
            method="POST",
        )
        self.delete_endpoint = Endpoint.objects.create(
            app_label="gida",
            route_path="api/3.0/gida/",
            route_name="gida-list",
            method="DELETE",
        )
        # Stats for the risky ones only; GET has no usage.
        EndpointStat.objects.create(
            endpoint=self.post_endpoint,
            date="2026-10-08",
            client_type="anon",
            status_class="2xx",
            count=3,
        )
        self.delete_stat = EndpointStat.objects.create(
            endpoint=self.delete_endpoint,
            date="2026-10-08",
            client_type="anon",
            status_class="2xx",
            count=1,
        )

    def endpoints(self, **params):
        response = self.client.get(reverse(ENDPOINT_CHANGELIST), params)
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset)

    def stats(self, **params):
        response = self.client.get(reverse(STAT_CHANGELIST), params)
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset)

    # -- endpoints ----------------------------------------------------------

    def test_endpoint_admin_filters_by_method(self):
        self.assertEqual(self.endpoints(method="POST"), {self.post_endpoint})

    def test_endpoint_admin_filters_by_application(self):
        self.assertEqual(self.endpoints(app_label="gida"), {self.delete_endpoint})

    def test_endpoint_admin_without_filter_lists_everything(self):
        self.assertEqual(
            self.endpoints(),
            {self.get_endpoint, self.post_endpoint, self.delete_endpoint},
        )

    # -- stats (through the endpoint) ---------------------------------------

    def test_stats_admin_filters_by_method(self):
        rows = self.stats(method="DELETE")
        self.assertEqual([row.endpoint for row in rows], [self.delete_endpoint])

    def test_stats_admin_filters_by_application(self):
        rows = self.stats(app_label="api")
        self.assertEqual([row.endpoint for row in rows], [self.post_endpoint])

    # -- columns ------------------------------------------------------------

    def test_stats_show_the_application_and_the_method_as_columns(self):
        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        # The columns exist and carry the endpoint's data (not just the titles).
        self.assertIn('class="field-application"', html)
        self.assertIn('class="field-method_badge"', html)
        self.assertIn(">gida</td>", html)

    def test_the_method_is_rendered_as_a_coloured_badge(self):
        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        # DELETE in red, POST in blue; the verb lives inside the pill.
        self.assertIn("background:#f8d7da", html)
        self.assertIn(">DELETE</span>", html)
        self.assertIn("background:#cfe2ff", html)
        self.assertIn(">POST</span>", html)

    def test_the_endpoint_column_shows_only_the_path(self):
        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        # The verb and the app have their own columns, so the cell carries just
        # the path. Asserted on the cells: from Django 5.1 on, the action
        # checkbox aria-label repeats str(obj), which includes the endpoint.
        cells = re.findall(r'<td class="field-endpoint_path">([^<]*)</td>', html)

        self.assertCountEqual(cells, ["api/3.0/artikuluak/", "api/3.0/gida/"])

    def test_the_endpoint_column_strips_the_regex_anchors(self):
        endpoint = Endpoint.objects.create(
            app_label="api", route_path="^api/3.0/eskelak/$", method="GET"
        )
        EndpointStat.objects.create(
            endpoint=endpoint,
            date="2026-10-08",
            client_type="anon",
            status_class="2xx",
            count=1,
        )

        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        self.assertIn(">api/3.0/eskelak/</td>", html)

    # -- filter presentation ------------------------------------------------

    def test_titles_are_readable_instead_of_raw_field_names(self):
        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        self.assertIn("Application", html)
        self.assertIn("Method", html)
        self.assertNotIn("Irizpidea: app label", html)

    def test_method_lookups_put_the_risky_ones_first(self):
        model_admin = django_admin.site._registry[Endpoint]
        list_filter = MethodListFilter(
            request=None, params={}, model=Endpoint, model_admin=model_admin
        )

        lookups = [value for value, _ in list_filter.lookups(None, model_admin)]

        self.assertEqual(lookups, ["DELETE", "POST", "GET"])

    def test_basque_catalog_is_shipped(self):
        with translation.override("eu"):
            html = self.client.get(reverse(ENDPOINT_CHANGELIST)).content.decode()

            self.assertIn("Aplikazioa", html)
            self.assertIn("Metodoa", html)

    def test_total_count_follows_the_active_language(self):
        with translation.override("eu"):
            html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()
            self.assertIn("GUZTIRA", html)

        with translation.override("en"):
            html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()
            self.assertIn("TOTAL COUNT", html)
