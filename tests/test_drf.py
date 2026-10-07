from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import RequestFactory, TestCase, override_settings

from django_api_usage.drf import HasAPIScope


class FakeView:
    required_scopes = ("content:write",)
    enforcement_key = "fake"


class NoScopeView:
    required_scopes = ()


class HasAPIScopeTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = FakeView()

    def _request(self, user=None):
        request = self.factory.get("/")
        request.user = user or AnonymousUser()
        return request

    @override_settings(API_ENFORCEMENT="report")
    def test_report_mode_allows_and_flags(self):
        request = self._request()
        self.assertTrue(HasAPIScope().has_permission(request, self.view))
        self.assertEqual(request._api_usage_would_deny, ["content:write"])

    @override_settings(API_ENFORCEMENT="enforce")
    def test_enforce_mode_denies_without_scopes(self):
        self.assertFalse(HasAPIScope().has_permission(self._request(), self.view))

    @override_settings(API_ENFORCEMENT="enforce")
    def test_view_without_required_scopes_is_denied(self):
        self.assertFalse(HasAPIScope().has_permission(self._request(), NoScopeView))

    @override_settings(API_ENFORCEMENT="enforce")
    def test_group_grants_scope(self):
        user = User.objects.create_user("someone", password="x")
        group = Group.objects.create(name="api:content:write")
        user.groups.add(group)

        request = self._request(user=user)
        self.assertTrue(HasAPIScope().has_permission(request, self.view))

    @override_settings(
        API_ENFORCEMENT="enforce", API_ENFORCEMENT_OVERRIDES={"fake": "report"}
    )
    def test_override_relaxes_a_single_view(self):
        request = self._request()
        self.assertTrue(HasAPIScope().has_permission(request, self.view))
