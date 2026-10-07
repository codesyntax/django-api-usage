from django.core.checks import run_checks
from django.test import TestCase, override_settings

from django_api_usage.checks import DUMMY_CACHE_BACKEND


class ChecksTest(TestCase):
    def _check_ids(self):
        return [issue.id for issue in run_checks()]

    def test_warns_when_middleware_is_not_installed(self):
        with override_settings(MIDDLEWARE=[]):
            self.assertIn("api_usage.W001", self._check_ids())

    def test_warns_when_buffer_cache_is_dummy(self):
        with override_settings(CACHES={"default": {"BACKEND": DUMMY_CACHE_BACKEND}}):
            self.assertIn("api_usage.W003", self._check_ids())

    def test_no_dummy_warning_with_a_real_cache(self):
        with override_settings(
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            }
        ):
            self.assertNotIn("api_usage.W003", self._check_ids())
