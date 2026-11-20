"""URL configuration. The Django admin site is intentionally not included."""

from django.urls import include, path

from config.health import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("", include("accounts.urls")),
    path("", include("customers.urls")),
    path("", include("audit.urls")),
]
