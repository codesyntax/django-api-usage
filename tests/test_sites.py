"""Tests for the Site column and filter.

Several front ends (several sites) can call the same backend, so the endpoint's
site is how they are told apart.
"""

import re

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.urls import reverse

from django_api_usage.admin import reset_site_labels_cache
from django_api_usage.models import Endpoint, EndpointStat

from .base import UsageTestCase

STAT_CHANGELIST = "admin:django_api_usage_endpointstat_changelist"
ENDPOINT_CHANGELIST = "admin:django_api_usage_endpoint_changelist"


class SiteColumnTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        # The labels are cached per process, so every test starts from scratch.
        reset_site_labels_cache()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)

        self.goiena = Site.objects.create(domain="goiena.eus", name="Goiena")
        self.arrasate = Site.objects.create(domain="arrasate.eus", name="Arrasate")

        self.endpoint_a = Endpoint.objects.create(
            site_id=self.goiena.pk,
            app_label="api",
            route_path="api/3.0/a/",
            method="GET",
        )
        self.endpoint_b = Endpoint.objects.create(
            site_id=self.arrasate.pk,
            app_label="api",
            route_path="api/3.0/b/",
            method="GET",
        )
        self.stat_a = EndpointStat.objects.create(
            endpoint=self.endpoint_a, date="2026-10-08", client_type="anon", count=1
        )
        self.stat_b = EndpointStat.objects.create(
            endpoint=self.endpoint_b, date="2026-10-08", client_type="anon", count=2
        )

    def cells(self, changelist, **params):
        html = self.client.get(reverse(changelist), params).content.decode()
        return re.findall(r'<td class="field-site">([^<]*)</td>', html)

    def rows(self, **params):
        response = self.client.get(reverse(STAT_CHANGELIST), params)
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset)

    # -- column -------------------------------------------------------------

    def test_the_stats_column_shows_the_domain(self):
        self.assertCountEqual(
            self.cells(STAT_CHANGELIST), ["goiena.eus", "arrasate.eus"]
        )

    def test_the_endpoints_column_shows_the_domain(self):
        self.assertCountEqual(
            self.cells(ENDPOINT_CHANGELIST), ["goiena.eus", "arrasate.eus"]
        )

    # -- filter -------------------------------------------------------------

    def test_the_stats_can_be_filtered_by_site(self):
        self.assertEqual(self.rows(site=self.goiena.pk), {self.stat_a})
        self.assertEqual(self.rows(site=self.arrasate.pk), {self.stat_b})

    def test_the_filter_offers_every_site_by_domain(self):
        html = self.client.get(reverse(STAT_CHANGELIST)).content.decode()

        self.assertIn(f"?site={self.goiena.pk}", html)
        self.assertIn(">goiena.eus</a>", html)
        self.assertIn(">arrasate.eus</a>", html)

    def test_the_endpoints_can_be_filtered_by_site(self):
        response = self.client.get(
            reverse(ENDPOINT_CHANGELIST), {"site": self.arrasate.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["cl"].queryset), {self.endpoint_b})
