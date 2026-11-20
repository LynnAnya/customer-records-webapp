"""Health check for Render: GET /healthz/ answers "ok" only when Django can
reach the database. A new version that cannot reach Neon never gets visitors.
Public (Render calls it without logging in) and reveals nothing."""

from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@login_not_required
@require_GET
@never_cache
def healthz(request: HttpRequest) -> HttpResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return HttpResponse(
            "database unavailable", status=503, content_type="text/plain"
        )
    return HttpResponse("ok", content_type="text/plain")
