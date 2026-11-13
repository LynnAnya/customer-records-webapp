"""URL configuration. The Django admin site is intentionally not included."""

from django.urls import include, path

urlpatterns = [
    path("", include("accounts.urls")),
    path("", include("customers.urls")),
    path("", include("audit.urls")),
]
