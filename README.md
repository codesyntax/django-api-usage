![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-api-usage?logo=pypi)
![Django versions](https://img.shields.io/badge/django-4.2%20%7C%205.2-0C4B33)
![Status](https://img.shields.io/badge/status-alpha-orange)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/codesyntax/django-api-usage/ci.yml?logo=github)
![PyPI - Version](https://img.shields.io/pypi/v/django-api-usage?logo=pypi)

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

## Admin

The package ships a read-only admin for the three models, built with plain
Django — **no dependency beyond Django itself** (no `django-object-actions` or
similar):

* **Endpoint stats** changelist: a search box (by endpoint path, route name, app,
  method or replacement), filters by date, client type, status class, and
  **Application** / **Method**, plus the **sum of the `count` column** for the
  rows matching the current filters. The Method filter lists the riskiest verbs
  first (`DELETE`, `POST`, ...), and the list shows **Application** and
  **Method** as columns — the verb as a coloured badge (writes amber, deletes
  red), so the dangerous traffic is obvious at a glance.
* **Endpoint** changelist: the same Application / Method filters, plus
  deprecation state, the site and the CSV export.
* **Flush now**: moves counters buffered in the cache into the database, so they
  appear immediately when you run with `BUFFER_BACKEND = "cache"`.
* **Clear statistics**: empties the aggregated counters behind a confirmation
  page (endpoints and their deprecation metadata are kept).
* **Export selected rows to CSV** on all three admins. Relations are flattened
  into one analysis-friendly table (a stat row carries its endpoint's path, app
  and method), so the file can be fed straight to pandas or a spreadsheet. Use
  the "select all" link to export every row matching the current filters.

## Client applications

Not every caller is a person: ERPs, partners, your own web front end and the
native mobile apps also hit the API. `ClientApp` is an **editable table**, and
the rules are checked in this order:

| # | Rule | Matched against | Use it for |
|---|---|---|---|
| 1 | `ClientAppAccount` | the authenticated account (and therefore its DRF token) | one dedicated token per integration (ERP, partner...) |
| 2 | `domains` | the `Origin`/`Referer` host, subdomains included | your own web front end |
| 3 | `ip_networks` | the client address, against a CIDR (one per line) | internal networks and servers |
| 4 | `user_agent_patterns` | a case-insensitive substring of `User-Agent` | native mobile apps |

An explicit assignment always wins: if the token's account belongs to an
application, that is the answer. Accounts without an assignment (an app user
reading the news) fall through to the user agent, which is what identifies the
native apps. `priority` decides between applications (lower wins), and a caller
matching nothing stays unattributed.

Assignments are one row per account (a point lookup, indexed) instead of a
many-to-many list holding every account, so nothing grows with the number of
users: `EndpointStat.client_app` only ever holds a `ClientApp.slug`.

Counters, the CSV export and the admin filters all carry the application, so
"which application calls this endpoint?" is one filter away. The **Endpoint
stats** changelist also offers *Not attributed*: the callers still to classify.

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

**Alpha.** The core is implemented: metering middleware, models and migrations,
management commands, the deprecation layer and a DRF shadow-mode permission.
Tested on Python 3.10-3.12 and Django 4.2/5.2. MIT licensed.

## Development

```bash
python -m django test tests --settings=tests.settings
ruff check .
black --check .
```
