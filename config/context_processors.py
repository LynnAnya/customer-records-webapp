from django.conf import settings
from django.http import HttpRequest


def site(request: HttpRequest) -> dict[str, str]:
    """Makes `SITE_NAME` (the name shown in the app) available in every template."""
    return {"SITE_NAME": settings.SITE_NAME}
