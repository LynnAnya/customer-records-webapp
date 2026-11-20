from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.permissions import admin_required
from audit.export import stream_csv
from audit.labels import ACTION_LABELS
from audit.models import ActivityLog
from audit.queries import LogFilters, activity_logs, parse_log_filters
from audit.services import get_client_ip, log_action

PAGE_SIZE = 50
# Above this many rows the page suggests the yearly archive (see CLAUDE.md).
ARCHIVE_HINT_ROWS = 100_000


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
        "archive_hint": page.paginator.count > ARCHIVE_HINT_ROWS
        and not filters.active_count,
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
    # Replace, never push: the 10-second refresh must not add Back entries.
    response["HX-Replace-Url"] = context["page_url"]
    return response


@admin_required
@require_GET
def activity_log_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One log row in full, with every customer name. Read-only."""
    entry = get_object_or_404(ActivityLog.objects.select_related("user"), pk=pk)
    back = request.GET.get("back", "")
    # Only our own log list may be the way back (never an outside address).
    if not back.startswith(reverse("activity_log")):
        back = reverse("activity_log")
    return render(request, "audit/detail.html", {"entry": entry, "back_url": back})


@admin_required
@require_POST
def activity_log_export(request: HttpRequest) -> StreamingHttpResponse:
    """Download the log as CSV: the current filters, or everything.

    POST because it writes a `log_exported` row first, like copy and PDF.
    """
    filters = (
        LogFilters()
        if request.POST.get("scope") == "all"
        else (parse_log_filters(request.POST))
    )
    # Freeze the set first, so the file and the logged count match exactly
    # (this download's own log row is not in the file).
    last_id = ActivityLog.objects.order_by("-id").values_list("id", flat=True).first()
    logs = activity_logs(filters).filter(id__lte=last_id or 0)
    log_action(
        ActivityLog.Action.LOG_EXPORTED,
        user=request.user,
        details={"count": logs.count()},
        ip_address=get_client_ip(request),
    )
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = StreamingHttpResponse(
        stream_csv(logs), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="activity-log-{stamp}.csv"'
    response["Cache-Control"] = "no-store"
    return response
