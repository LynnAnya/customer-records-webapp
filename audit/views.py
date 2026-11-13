from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.permissions import admin_required
from audit.labels import ACTION_LABELS
from audit.queries import activity_logs, parse_log_filters

PAGE_SIZE = 50


def _log_context(request: HttpRequest) -> dict:
    filters = parse_log_filters(request.GET)
    page = Paginator(activity_logs(filters), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    params = filters.as_params()
    if page.number > 1:
        params["page"] = str(page.number)
    query = urlencode(params)
    users = get_user_model().objects.order_by("username")
    return {
        "page": page,
        "filters": filters,
        "user_options": users,
        "action_options": ACTION_LABELS.items(),
        "updated_at": timezone.localtime(),
        "page_url": f"{reverse('activity_log')}?{query}"
        if query
        else reverse("activity_log"),
    }


@admin_required
@require_GET
def activity_log(request: HttpRequest) -> HttpResponse:
    """Read-only list of everything users did. Admins only."""
    return render(request, "audit/list.html", _log_context(request))


@admin_required
@require_GET
def activity_log_table(request: HttpRequest) -> HttpResponse:
    """Only the table, for filters, paging and the 10-second refresh."""
    context = _log_context(request)
    response = render(request, "audit/list.html#table", context)
    response["HX-Push-Url"] = context["page_url"]
    return response
