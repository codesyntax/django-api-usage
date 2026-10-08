"""Read-only admin for usage counters, with two maintenance buttons.

* **Flush now** moves counters buffered in the cache to the database, so they
  show up here immediately when ``BUFFER_BACKEND = "cache"``.
* **Clear statistics** empties the aggregated counters. Endpoints (and their
  deprecation metadata) are kept on purpose.

The changelist also shows the **sum of the ``count`` column** for the rows that
match the current filters, and every admin ships an **export to CSV** action for
the selected rows (all the rows matching the filters can be selected with the
"select all" link).

Everything is plain Django: no extra dependency beyond Django itself.
"""

import csv

from django.contrib import admin, messages
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from .buffers import flush
from .models import Consumer, Endpoint, EndpointStat


class CsvExportMixin:
    """Admin action to download the selected rows as CSV.

    ``csv_columns`` is an iterable of ``(header, queryset lookup)`` pairs. The
    lookups are resolved by the database in a single query, so related rows can
    be flattened into one analysis-friendly table (for example a stat row plus
    its endpoint's path and app label).
    """

    #: ``(header, lookup)`` pairs. The header is written as-is (keep it stable
    #: and ASCII: the file is meant to be read by pandas or a spreadsheet).
    csv_columns = ()
    #: Prefix of the downloaded filename; the date is appended.
    csv_filename_prefix = "django-api-usage"

    @admin.action(description=_("Export selected rows to CSV"))
    def export_as_csv(self, request, queryset):
        columns = list(self.csv_columns)
        rows = queryset.values_list(*(lookup for _, lookup in columns))

        filename = f"{self.csv_filename_prefix}-{timezone.localdate():%Y-%m-%d}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        # Byte order mark, so Excel detects UTF-8 (content may be Basque).
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow([header for header, _ in columns])
        writer.writerows(rows)
        return response


@admin.register(Endpoint)
class EndpointAdmin(CsvExportMixin, admin.ModelAdmin):
    actions = ("export_as_csv",)
    csv_columns = (
        ("app_label", "app_label"),
        ("route_path", "route_path"),
        ("route_name", "route_name"),
        ("method", "method"),
        ("site_id", "site_id"),
        ("deprecated", "deprecated"),
        ("sunset_date", "sunset_date"),
        ("replacement", "replacement"),
        ("owner", "owner"),
        ("notes", "notes"),
    )
    list_display = (
        "app_label",
        "route_path",
        "route_name",
        "method",
        "site_id",
        "deprecated",
        "sunset_date",
        "replacement",
        "owner",
    )
    list_filter = ("deprecated", "app_label", "method", "site_id")
    search_fields = ("route_path", "route_name", "replacement", "owner", "notes")
    list_editable = ("deprecated", "sunset_date", "replacement", "owner")


@admin.register(EndpointStat)
class EndpointStatAdmin(CsvExportMixin, admin.ModelAdmin):
    actions = ("export_as_csv",)
    # Flattened on purpose: the CSV is meant for analysis (pandas, spreadsheet)
    # without having to join endpoints by hand.
    csv_columns = (
        ("date", "date"),
        ("app_label", "endpoint__app_label"),
        ("route_path", "endpoint__route_path"),
        ("route_name", "endpoint__route_name"),
        ("method", "endpoint__method"),
        ("site_id", "endpoint__site_id"),
        ("client_type", "client_type"),
        ("status_class", "status_class"),
        ("count", "count"),
    )
    list_display = ("date", "endpoint", "client_type", "status_class", "count")
    list_filter = ("date", "client_type", "status_class")
    list_select_related = ("endpoint",)
    date_hierarchy = "date"
    # Search across the related endpoint (case-insensitive "contains").
    search_fields = (
        "endpoint__route_path",
        "endpoint__route_name",
        "endpoint__app_label",
        "endpoint__method",
        "endpoint__replacement",
    )
    search_help_text = _(
        "Search by endpoint path, route name, app, method or replacement (for "
        "example 'herriak' or 'artikuluak')."
    )
    change_list_template = "admin/django_api_usage/endpointstat/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # -- changelist total ---------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        """Add the sum of ``count`` over the *filtered* queryset to the context."""
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            changelist = response.context_data["cl"]
        except (AttributeError, KeyError):
            return response
        response.context_data["usage_total"] = (
            changelist.queryset.aggregate(total=Sum("count"))["total"] or 0
        )
        return response

    # -- custom maintenance views -------------------------------------------

    def get_urls(self):
        app_label, model_name = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                "flush/",
                self.admin_site.admin_view(self.flush_view),
                name=f"{app_label}_{model_name}_flush",
            ),
            path(
                "clear/",
                self.admin_site.admin_view(self.clear_view),
                name=f"{app_label}_{model_name}_clear",
            ),
        ]
        return custom + super().get_urls()

    def _changelist_url(self):
        app_label, model_name = self.opts.app_label, self.opts.model_name
        return reverse(f"admin:{app_label}_{model_name}_changelist")

    def flush_view(self, request):
        """Move buffered counters from the cache into the database."""
        if request.method != "POST":
            return HttpResponseRedirect(self._changelist_url())
        written = flush()
        if written:
            self.message_user(
                request,
                format_lazy(_("Flushed {count} buffered counter(s)."), count=written),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _(
                    "Nothing was buffered: with BUFFER_BACKEND='db' counters are "
                    "already in the database."
                ),
                messages.INFO,
            )
        return HttpResponseRedirect(self._changelist_url())

    def clear_view(self, request):
        """Empty the aggregated counters (a confirmation page is shown first)."""
        if request.method != "POST":
            context = {
                **self.admin_site.each_context(request),
                "title": _("Clear statistics"),
                "opts": self.opts,
                "total": EndpointStat.objects.count(),
            }
            return TemplateResponse(
                request,
                "admin/django_api_usage/endpointstat/confirm_clear.html",
                context,
            )
        deleted = EndpointStat.objects.all().delete()[0]
        self.message_user(
            request,
            format_lazy(_("Deleted {count} statistic row(s)."), count=deleted),
            messages.SUCCESS,
        )
        return HttpResponseRedirect(self._changelist_url())


@admin.register(Consumer)
class ConsumerAdmin(CsvExportMixin, admin.ModelAdmin):
    actions = ("export_as_csv",)
    csv_columns = (
        ("kind", "kind"),
        ("ref_hash", "ref_hash"),
        ("user_agent_family", "user_agent_family"),
        ("request_count", "request_count"),
        ("first_seen", "first_seen"),
        ("last_seen", "last_seen"),
        ("contact", "contact"),
        ("notes", "notes"),
    )
    list_display = (
        "kind",
        "ref_short",
        "user_agent_family",
        "request_count",
        "first_seen",
        "last_seen",
        "contact",
    )
    list_filter = ("kind",)
    search_fields = ("contact", "notes")
    list_editable = ("contact",)

    @admin.display(description="Reference")
    def ref_short(self, obj):
        return obj.ref_hash[:12]
