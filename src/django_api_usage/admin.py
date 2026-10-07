"""Read-only admin for usage counters, plus editable deprecation metadata."""

from django.contrib import admin

from .models import Consumer, Endpoint, EndpointStat


@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
    list_display = (
        "app_label",
        "route_name",
        "method",
        "site_id",
        "deprecated",
        "sunset_date",
        "replacement",
        "owner",
    )
    list_filter = ("deprecated", "app_label", "method", "site_id")
    search_fields = ("route_name", "replacement", "owner", "notes")
    list_editable = ("deprecated", "sunset_date", "replacement", "owner")


@admin.register(EndpointStat)
class EndpointStatAdmin(admin.ModelAdmin):
    list_display = ("date", "endpoint", "client_type", "status_class", "count")
    list_filter = ("date", "client_type", "status_class")
    list_select_related = ("endpoint",)
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
