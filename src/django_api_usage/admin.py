"""Read-only admin for usage counters, with two maintenance buttons.

* **Flush now** moves counters buffered in the cache to the database, so they
  show up here immediately when ``BUFFER_BACKEND = "cache"``.
* **Clear statistics** empties the aggregated counters. Endpoints (and their
  deprecation metadata) are kept on purpose.

The changelist also shows the **sum of the ``count`` column** for the rows that
match the current filters.
"""

from django.contrib import admin, messages
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from .buffers import flush
from .models import Consumer, Endpoint, EndpointStat


@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
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
class EndpointStatAdmin(admin.ModelAdmin):
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
class ConsumerAdmin(admin.ModelAdmin):
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
