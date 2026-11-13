"""Reading the activity log for the admin page. Nothing here writes."""

from dataclasses import dataclass
from datetime import date

from django.db.models import QuerySet
from django.http import QueryDict
from django.utils.dateparse import parse_date

from audit.models import ActivityLog


@dataclass(frozen=True)
class LogFilters:
    user_id: int | None = None
    action: str = ""
    date_from: date | None = None
    date_to: date | None = None

    def as_params(self) -> dict[str, str]:
        params = {
            "user": str(self.user_id) if self.user_id else "",
            "action": self.action,
            "from": self.date_from.isoformat() if self.date_from else "",
            "to": self.date_to.isoformat() if self.date_to else "",
        }
        return {key: value for key, value in params.items() if value}

    @property
    def active_count(self) -> int:
        return len(self.as_params())


def _safe_date(value: str | None) -> date | None:
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def parse_log_filters(params: QueryDict) -> LogFilters:
    """Build filters from the URL. Anything invalid is ignored."""
    user = params.get("user", "")
    action = params.get("action", "")
    return LogFilters(
        user_id=int(user)
        if user.isascii() and user.isdigit() and len(user) <= 12
        else None,
        action=action if action in ActivityLog.Action.values else "",
        date_from=_safe_date(params.get("from")),
        date_to=_safe_date(params.get("to")),
    )


def activity_logs(filters: LogFilters | None = None) -> QuerySet[ActivityLog]:
    """Log rows, newest first."""
    logs = ActivityLog.objects.select_related("user").order_by("-created_at", "-id")
    if not filters:
        return logs
    if filters.user_id:
        logs = logs.filter(user_id=filters.user_id)
    if filters.action:
        logs = logs.filter(action=filters.action)
    if filters.date_from:
        logs = logs.filter(created_at__date__gte=filters.date_from)
    if filters.date_to:
        logs = logs.filter(created_at__date__lte=filters.date_to)
    return logs
