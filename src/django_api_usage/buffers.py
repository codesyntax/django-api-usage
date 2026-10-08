"""Recording backends.

The default backend accumulates counters in a single cache key and flushes them
to the database in batches (``api_usage_flush``), so a request never pays a
database write. With ``FAIL_OPEN`` metering can never break a request.

Note: the cache backend trades perfect accuracy under high concurrency for
throughput. If you need per-request exactness, set ``BUFFER_BACKEND = "db"``.
"""

import json
import logging

from django.core.cache import caches
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .conf import api_settings
from .models import Consumer, Endpoint, EndpointStat

logger = logging.getLogger("django_api_usage")

# The dimensions stored per bucket. Route patterns may contain any character,
# so a bucket is encoded as JSON rather than with a separator.
_FIELDS = (
    "site_id",
    "app_label",
    "route_name",
    "route_path",
    "method",
    "client_type",
)


def _cache():
    return caches[api_settings.CACHE_ALIAS]


def _buffer_key():
    return f"{api_settings.CACHE_PREFIX}:buffer"


def status_class(status_code):
    """``204`` -> ``2xx``."""
    return f"{int(status_code) // 100}xx"


def record_hit(dimensions, status_code, consumer=None):
    """Record a single hit.

    ``dimensions`` is a mapping with the keys in :data:`_FIELDS`.
    """
    if api_settings.BUFFER_BACKEND == "db":
        _write_to_db(dimensions, status_class(status_code), 1)
    else:
        _buffer(dimensions, status_class(status_code))
    if consumer and api_settings.TRACK_CONSUMERS:
        _touch_consumer(consumer)


def _bucket_key(dimensions, status_code_class):
    payload = {field: dimensions.get(field) for field in _FIELDS}
    return json.dumps([payload, status_code_class], sort_keys=True)


def _buffer(dimensions, status_code_class):
    cache = _cache()
    key = _buffer_key()
    raw = cache.get(key)
    counters = json.loads(raw) if raw else {}
    bucket = _bucket_key(dimensions, status_code_class)
    counters[bucket] = counters.get(bucket, 0) + 1
    cache.set(key, json.dumps(counters), None)


def flush():
    """Move buffered counters from the cache into the database.

    Returns the number of counter buckets written.
    """
    cache = _cache()
    key = _buffer_key()
    raw = cache.get(key)
    if not raw:
        return 0
    cache.delete(key)
    counters = json.loads(raw) if isinstance(raw, str) else raw
    written = 0
    for bucket, count in counters.items():
        try:
            payload, status_code_class = json.loads(bucket)
            dimensions = {field: payload.get(field) for field in _FIELDS}
        except (TypeError, ValueError):
            logger.warning("django-api-usage: skipping unreadable bucket %r", bucket)
            continue
        dimensions["site_id"] = _as_int(dimensions.get("site_id"))
        _write_to_db(dimensions, status_code_class, count)
        written += 1
    return written


def _as_int(value):
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _write_to_db(dimensions, status_code_class, count):
    route_path = dimensions.get("route_path") or ""
    with transaction.atomic():
        endpoint, created = Endpoint.objects.get_or_create(
            site_id=dimensions.get("site_id"),
            app_label=dimensions.get("app_label") or "unknown",
            route_name=dimensions.get("route_name") or "unknown",
            method=dimensions.get("method") or "GET",
            defaults={"route_path": route_path},
        )
        # Backfill the path for rows created before the field existed.
        if not created and route_path and not endpoint.route_path:
            Endpoint.objects.filter(pk=endpoint.pk).update(route_path=route_path)
        stat, created = EndpointStat.objects.get_or_create(
            endpoint=endpoint,
            date=timezone.localdate(),
            client_type=dimensions.get("client_type") or "anon",
            status_class=status_code_class,
            defaults={"count": count},
        )
        if not created:
            EndpointStat.objects.filter(pk=stat.pk).update(count=F("count") + count)


def _touch_consumer(consumer):
    kind, ref_hash, user_agent_family = consumer
    now = timezone.now()
    obj, created = Consumer.objects.get_or_create(
        kind=kind,
        ref_hash=ref_hash,
        defaults={
            "user_agent_family": user_agent_family,
            "first_seen": now,
            "last_seen": now,
            "request_count": 1,
        },
    )
    if created:
        return
    Consumer.objects.filter(pk=obj.pk).update(
        last_seen=now,
        request_count=F("request_count") + 1,
        user_agent_family=user_agent_family,
    )
