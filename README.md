# django-api-usage

Lightweight, privacy-first **usage metering for Django APIs**, with an optional
**deprecation lifecycle** layer on top.

It answers two questions that decide whether an endpoint can be changed or removed:

1. **How much is this endpoint (or this whole Django app) used?**
2. **Who is calling it, so they can be contacted before it changes?**

The package is deliberately generic: the core is plain Django middleware (works
with or without Django REST Framework), it never breaks a request because
metering failed, and it stores no raw personal data by default.

## Why not just `drf-api-tracking`?

`drf-api-tracking` stores one database row per request (including bodies), which
is heavy and privacy-sensitive. `django-api-usage` accumulates **counters** and
keeps consumer attribution **hashed and opt-in**. That makes it suitable both for
continuous usage analytics and for the concrete decision of deprecating an
endpoint.

## Install

```bash
pip install django-api-usage
```

```python
INSTALLED_APPS = [
    # ...
    "django_api_usage",
]

MIDDLEWARE = [
    # ...
    "django_api_usage.middleware.ApiUsageMiddleware",
]
```

Metering starts immediately. Counters are buffered in the cache and written to
the database in batches:

```bash
python manage.py api_usage_flush      # from cron, or a Celery beat task
python manage.py api_usage_report --days 30
python manage.py api_usage_report --days 90 --sunset-candidates
```

With Celery (and the `celery` extra) two tasks are provided:
`django_api_usage.tasks.flush_api_usage` and
`django_api_usage.tasks.prune_api_usage`.

## Configuration

```python
API_USAGE = {
    "ENABLED": True,
    "FAIL_OPEN": True,
    "BUFFER_BACKEND": "cache",       # "cache" (batched) or "db" (write per request)
    "RETENTION_DAYS": 90,
    "TRACK_CONSUMERS": False,        # opt-in; stores hashed callers only
    "CONSUMER_SALT": "a-rotatable-secret",
}
```

All resolvers are overridable, so no project-specific knowledge leaks into the
package:

```python
API_USAGE = {
    "APP_LABEL_RESOLVER": "myproject.api.resolvers.app_label",
    "SITE_RESOLVER": "myproject.api.resolvers.site_id",
    "ROLE_SCOPES_RESOLVER": "myproject.api.resolvers.role_scopes",
}
```

## Deprecation lifecycle

`Endpoint` carries `deprecated`, `sunset_date`, `replacement` and `owner`, so the
same data that measures usage also drives a deprecation plan. See the consuming
project's migration guide for the full workflow (measure → notify → enforce).

## DRF shadow mode

`django_api_usage.drf.HasAPIScope` enforces scopes declared on a view:

```python
class AllUserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasAPIScope]
    required_scopes = ["user:read_all"]
```

With `API_ENFORCEMENT = "report"` (the default) nothing is blocked yet: a
`X-Api-Would-Deny` header is returned instead, so you can deploy a permission and
measure what it *would* have denied before enforcing it.

## Status

Alpha. Skeleton with the core implemented; migrations, admin and tests included.
License and packaging metadata still to be finalised.

## Development

```bash
python -m django test tests --settings=tests.settings
ruff check .
black --check .
```
