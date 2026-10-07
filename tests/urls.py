from django.http import HttpResponse
from django.urls import path


def ping(request):
    return HttpResponse("ok")


def boom(request):
    return HttpResponse("nope", status=500)


urlpatterns = [
    path("ping/", ping, name="ping"),
    path("boom/", boom, name="boom"),
]
