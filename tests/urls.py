from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def ping(request):
    return HttpResponse("ok")


def boom(request):
    return HttpResponse("nope", status=500)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("ping/", ping, name="ping"),
    path("boom/", boom, name="boom"),
]
