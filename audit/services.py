import ipaddress
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest

from audit.models import ActivityLog

# Only these keys may go into `details`. Phone and account numbers have no key
# here on purpose, so they cannot be logged by accident.
ALLOWED_DETAIL_KEYS = frozenset(
    {"customer_ids", "customer_names", "count", "target_username", "previous_username"}
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


def get_client_ip(request: HttpRequest) -> str:
    """The visitor's own internet address.

    Live on Render, every request first passes Cloudflare and Render's proxy, so
    REMOTE_ADDR is the proxy, the same for everyone. Cloudflare writes the real
    address into CF-Connecting-IP and overwrites any copy the visitor sends, so
    it cannot be faked (X-Forwarded-For can: Cloudflare only appends to it).
    Only trusted when TRUST_CF_CONNECTING_IP is on (Render); on a laptop the
    header could be typed by anyone. Used by the QR rate limit, the login
    lockout (axes) and the activity log.
    """
    if settings.TRUST_CF_CONNECTING_IP:
        real_ip = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
        if _is_ip(real_ip):
            return real_ip
    return request.META.get("REMOTE_ADDR", "")


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
