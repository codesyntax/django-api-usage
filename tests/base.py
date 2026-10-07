from django.core.cache import cache
from django.test import TestCase


class UsageTestCase(TestCase):
    """Base test case that isolates the usage buffer.

    Django does not reset the cache between tests, and the default
    ``BUFFER_BACKEND`` accumulates counters there, so clear it explicitly.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
