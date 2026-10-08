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
from django.db.models import Count, OuterRef, Subquery, Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from .buffers import flush
from .models import ClientApp, ClientAppAccount, Consumer, Endpoint, EndpointStat


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


#: HTTP methods, riskiest first: the point of the filter is spotting the
#: write/destructive calls (POST, DELETE, ...) instead of the read ones.
METHOD_ORDER = ("DELETE", "POST", "PUT", "PATCH", "GET", "HEAD", "OPTIONS")


class AppLabelListFilter(admin.SimpleListFilter):
    """Distinct application labels, under a readable title."""

    title = _("Application")
    parameter_name = "app_label"
    #: Lookup against the admin's model; overridden for related filters.
    field_path = "app_label"

    def lookups(self, request, model_admin):
        values = (
            model_admin.model.objects.order_by()
            .values_list(self.field_path, flat=True)
            .distinct()
        )
        return [(value, value) for value in sorted(v for v in values if v)]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(**{self.field_path: self.value()})


class MethodListFilter(admin.SimpleListFilter):
    """HTTP methods, riskiest (DELETE, POST, ...) first."""

    title = _("Method")
    parameter_name = "method"
    field_path = "method"

    def lookups(self, request, model_admin):
        values = set(
            model_admin.model.objects.order_by()
            .values_list(self.field_path, flat=True)
            .distinct()
        )
        ordered = [method for method in METHOD_ORDER if method in values]
        rest = sorted(m for m in values if m and m not in METHOD_ORDER)
        return [(method, method) for method in ordered + rest]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(**{self.field_path: self.value()})


class StatAppLabelListFilter(AppLabelListFilter):
    """Application filter for the stats changelist (through the endpoint)."""

    field_path = "endpoint__app_label"


class StatMethodListFilter(MethodListFilter):
    """Method filter for the stats changelist (through the endpoint)."""

    field_path = "endpoint__method"


#: Sentinel for the calls that could not be attributed to any application.
UNATTRIBUTED = "__none__"


class ClientAppListFilter(admin.SimpleListFilter):
    """Client applications, plus the calls that were not attributed.

    Applications defined in the table are listed even before they have traffic,
    which is what you want while checking that a new rule works.
    """

    title = _("Client application")
    parameter_name = "client_app"

    def lookups(self, request, model_admin):
        used = set(
            model_admin.model.objects.order_by()
            .values_list("client_app", flat=True)
            .distinct()
        )
        names = dict(ClientApp.objects.values_list("slug", "name"))
        defined = set(
            ClientApp.objects.filter(is_active=True).values_list("slug", flat=True)
        )
        choices = [
            (slug, names.get(slug) or slug) for slug in sorted((used | defined) - {""})
        ]
        choices.append((UNATTRIBUTED, _("Not attributed")))
        return choices

    def queryset(self, request, queryset):
        value = self.value()
        if value == UNATTRIBUTED:
            return queryset.filter(client_app="")
        if value:
            return queryset.filter(client_app=value)
        return queryset


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
    list_filter = (
        "deprecated",
        AppLabelListFilter,
        MethodListFilter,
        "site_id",
    )
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
        ("client_app", "client_app"),
        ("status_class", "status_class"),
        ("count", "count"),
    )
    list_display = (
        "date",
        "endpoint",
        "client_type",
        "client_app",
        "status_class",
        "count",
    )
    list_filter = (
        "date",
        "client_type",
        ClientAppListFilter,
        "status_class",
        StatAppLabelListFilter,
        StatMethodListFilter,
    )
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


@admin.register(ClientApp)
class ClientAppAdmin(CsvExportMixin, admin.ModelAdmin):
    """Editable table: recognise a new consumer without deploying anything."""

    actions = ("export_as_csv",)
    csv_columns = (
        ("slug", "slug"),
        ("name", "name"),
        ("priority", "priority"),
        ("is_active", "is_active"),
        ("domains", "domains"),
        ("ip_networks", "ip_networks"),
        ("user_agent_patterns", "user_agent_patterns"),
    )
    list_display = (
        "slug",
        "name",
        "priority",
        "is_active",
        "accounts_total",
        "counters_total",
    )
    list_filter = ("is_active",)
    search_fields = ("slug", "name", "description")
    fieldsets = (
        (None, {"fields": ("slug", "name", "description", "priority", "is_active")}),
        (
            _("Matching rules"),
            {
                "fields": ("domains", "ip_networks", "user_agent_patterns"),
                "description": _(
                    "Checked in this order: account, request host, client "
                    "network, user agent. Between applications, the lowest "
                    "priority wins. Accounts are assigned from the "
                    "'Client application accounts' table."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        counters = (
            EndpointStat.objects.filter(client_app=OuterRef("slug"))
            .order_by()
            .values("client_app")
            .annotate(total=Sum("count"))
            .values("total")
        )
        return (
            super()
            .get_queryset(request)
            .annotate(accounts_total=Count("accounts", distinct=True))
            .annotate(counters_total=Subquery(counters))
        )

    @admin.display(description=_("Accounts"), ordering="accounts_total")
    def accounts_total(self, obj):
        return obj.accounts_total

    @admin.display(description=_("Counters"), ordering="counters_total")
    def counters_total(self, obj):
        return obj.counters_total or 0


@admin.register(ClientAppAccount)
class ClientAppAccountAdmin(CsvExportMixin, admin.ModelAdmin):
    """One row per assigned account: search, do not scroll a giant list."""

    actions = ("export_as_csv",)
    csv_columns = (
        ("client_app", "client_app__slug"),
        ("username", "user__username"),
        ("email", "user__email"),
        ("notes", "notes"),
    )
    list_display = ("client_app", "account", "notes")
    list_filter = ("client_app",)
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "notes",
    )
    raw_id_fields = ("user",)
    list_select_related = ("user", "client_app")

    @admin.display(description=_("Account"), ordering="user__username")
    def account(self, obj):
        return obj.user
