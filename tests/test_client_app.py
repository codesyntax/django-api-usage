"""Tests for the editable ClientApp table and its matching rules."""

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from django_api_usage.buffers import flush
from django_api_usage.models import ClientApp, ClientAppAccount, Endpoint, EndpointStat
from django_api_usage.resolvers import client_app_from_rules, reset_client_app_cache

from .base import UsageTestCase

STAT_CHANGELIST = "admin:django_api_usage_endpointstat_changelist"


class ClientAppResolverTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        reset_client_app_cache()
        self.factory = RequestFactory()

    def request(self, user=None, **meta):
        request = self.factory.get("/api/3.0/artikuluak/", **meta)
        if user is not None:
            request.user = user
        return request

    def test_a_dedicated_account_wins(self):
        """A dedicated token (its user) identifies the integration."""
        user = User.objects.create_user("zoho", "zoho@example.com", "pw")
        app = ClientApp.objects.create(slug="zoho", priority=10)
        ClientAppAccount.objects.create(client_app=app, user=user)

        self.assertEqual(client_app_from_rules(self.request(user=user)), "zoho")

    def test_an_account_of_an_inactive_application_is_ignored(self):
        user = User.objects.create_user("zaharra", "z@example.com", "pw")
        app = ClientApp.objects.create(slug="zaharra", is_active=False)
        ClientAppAccount.objects.create(client_app=app, user=user)

        self.assertEqual(client_app_from_rules(self.request(user=user)), "")

    def test_the_account_rule_wins_over_the_user_agent(self):
        user = User.objects.create_user("erp", "erp@example.com", "pw")
        erp = ClientApp.objects.create(slug="goiena_erp")
        ClientAppAccount.objects.create(client_app=erp, user=user)
        ClientApp.objects.create(slug="mugikorra", user_agent_patterns="tokio")

        request = self.request(user=user, HTTP_USER_AGENT="tokio/1")

        self.assertEqual(client_app_from_rules(request), "goiena_erp")

    def test_the_request_host_matches_subdomains(self):
        ClientApp.objects.create(slug="elhuyar", domains="elhuyar.eus")

        request = self.request(HTTP_ORIGIN="https://www.elhuyar.eus/tresnak")

        self.assertEqual(client_app_from_rules(request), "elhuyar")

    def test_the_client_network_matches(self):
        ClientApp.objects.create(
            slug="goiena_erp", ip_networks="10.0.0.0/8\n192.168.1.0/24"
        )

        self.assertEqual(
            client_app_from_rules(self.request(REMOTE_ADDR="10.1.2.3")), "goiena_erp"
        )

    def test_the_user_agent_matches_for_anonymous_readers(self):
        """The bulk of the traffic: readers on the native mobile apps."""
        ClientApp.objects.create(slug="mugikorra", user_agent_patterns="TokikomApp")

        request = self.request(HTTP_USER_AGENT="TokikomApp/2.1 (Android 15)")

        self.assertEqual(client_app_from_rules(request), "mugikorra")

    def test_everything_else_is_not_attributed(self):
        ClientApp.objects.create(slug="mugikorra", user_agent_patterns="TokikomApp")

        self.assertEqual(client_app_from_rules(self.request()), "")

    def test_the_lowest_priority_wins(self):
        ClientApp.objects.create(
            slug="orokorra", user_agent_patterns="tokio", priority=100
        )
        ClientApp.objects.create(
            slug="mugikorra", user_agent_patterns="tokio", priority=10
        )

        self.assertEqual(
            client_app_from_rules(self.request(HTTP_USER_AGENT="tokio/1")), "mugikorra"
        )

    def test_inactive_applications_are_ignored(self):
        ClientApp.objects.create(
            slug="zaharra", user_agent_patterns="tokio", is_active=False
        )

        self.assertEqual(
            client_app_from_rules(self.request(HTTP_USER_AGENT="tokio/1")), ""
        )

    def test_invalid_networks_are_skipped(self):
        ClientApp.objects.create(slug="gaizki", ip_networks="not-a-network")

        self.assertEqual(
            client_app_from_rules(self.request(REMOTE_ADDR="10.1.2.3")), ""
        )

    def test_saving_a_rule_invalidates_the_cache(self):
        self.assertEqual(client_app_from_rules(self.request()), "")

        ClientApp.objects.create(slug="berria", domains="berria.eus")

        request = self.request(HTTP_ORIGIN="https://berria.eus")
        self.assertEqual(client_app_from_rules(request), "berria")

    def test_middleware_stores_the_application_in_the_counters(self):
        ClientApp.objects.create(slug="mugikorra", user_agent_patterns="TokikomApp")

        self.client.get("/ping/", HTTP_USER_AGENT="TokikomApp/2.1")
        flush()

        self.assertEqual(EndpointStat.objects.get().client_app, "mugikorra")


class ClientAppAdminTest(UsageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)
        self.endpoint = Endpoint.objects.create(
            app_label="api", route_path="api/3.0/artikuluak/", method="GET"
        )
        self.attributed = EndpointStat.objects.create(
            endpoint=self.endpoint,
            date="2026-10-08",
            client_app="mugikorra",
            count=2,
        )
        self.unattributed = EndpointStat.objects.create(
            endpoint=self.endpoint,
            date="2026-10-08",
            client_type="user",
            client_app="",
            count=5,
        )

    def rows(self, **params):
        response = self.client.get(reverse(STAT_CHANGELIST), params)
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset)

    def test_the_table_is_editable_in_the_admin(self):
        app = ClientApp.objects.create(slug="mugikorra", name="Mugikorra")

        response = self.client.get(
            reverse("admin:django_api_usage_clientapp_change", args=[app.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matching rules")

    def test_account_assignments_are_editable_in_the_admin(self):
        app = ClientApp.objects.create(slug="zoho", name="Zoho")
        account = User.objects.create_user("zoho_erabiltzailea", "z@example.com", "pw")
        ClientAppAccount.objects.create(client_app=app, user=account)

        listing = self.client.get(
            reverse("admin:django_api_usage_clientappaccount_changelist")
        )

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "zoho_erabiltzailea")

        add_page = self.client.get(
            reverse("admin:django_api_usage_clientappaccount_add")
        )
        self.assertEqual(add_page.status_code, 200)

    def test_stats_can_be_filtered_by_application(self):
        self.assertEqual(self.rows(client_app="mugikorra"), {self.attributed})

    def test_stats_can_be_filtered_by_unattributed_calls(self):
        self.assertEqual(self.rows(client_app="__none__"), {self.unattributed})

    def test_applications_without_traffic_are_still_offered(self):
        ClientApp.objects.create(slug="erp", name="ERP")

        response = self.client.get(reverse(STAT_CHANGELIST))

        self.assertContains(response, "?client_app=erp")
        self.assertContains(response, ">ERP</a>")
