from typing import Any

from django.contrib.auth.models import AbstractBaseUser

from audit.models import ActivityLog

# Only these keys may go into `details`. Phone and account numbers have no key
# here on purpose, so they cannot be logged by accident.
ALLOWED_DETAIL_KEYS = frozenset(
    {"customer_ids", "customer_names", "count", "target_username"}
)


def log_action(
    action: ActivityLog.Action,
    *,
    user: AbstractBaseUser | None = None,
    username: str = "",
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> ActivityLog:
    """The only writer to the activity log. Writes exactly one row.

    Pass `username` without `user` for failed logins.
    """
    details = details or {}
    unknown = set(details) - ALLOWED_DETAIL_KEYS
    if unknown:
        raise ValueError(f"Keys not allowed in log details: {sorted(unknown)}")

    return ActivityLog.objects.create(
        action=ActivityLog.Action(action),
        user=user,
        username=user.get_username() if user else username,
        details=details,
        ip_address=ip_address,
    )
