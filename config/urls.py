"""URL configuration. The Django admin site is intentionally not included."""

from django.urls import include, path

urlpatterns = [
    path("", include("customers.urls")),
]
