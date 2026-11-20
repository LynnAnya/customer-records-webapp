"""URL configuration. The Django admin site is intentionally not included."""

from django.contrib.auth.decorators import login_not_required
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from config.health import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    # Some browsers ask for /favicon.ico whatever the page says; send them to the icon.
    path(
        "favicon.ico",
        login_not_required(RedirectView.as_view(url=static("img/favicon.svg"))),
    ),
    path("", include("accounts.urls")),
    path("", include("customers.urls")),
    path("", include("audit.urls")),
]
