from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def ping(request):
    return HttpResponse("ok")


def boom(request):
    return HttpResponse("nope", status=500)


def shadow(request):
    """Simulate a permission in shadow mode that would deny the call."""
    request._api_usage_would_deny = {"content:write"}
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("ping/", ping, name="ping"),
    path("boom/", boom, name="boom"),
    path("shadow/", shadow, name="shadow"),
]
