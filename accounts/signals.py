"""Write logins and failed logins to the activity log."""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from audit.models import ActivityLog
from audit.services import get_client_ip, log_action


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs) -> None:
    ip_address = get_client_ip(request) if request else None
    log_action(ActivityLog.Action.LOGIN, user=user, ip_address=ip_address or None)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs) -> None:
    # Only the typed username is kept. The password is never read here.
    username = str(credentials.get("username") or "")[:150]
    ip_address = get_client_ip(request) if request else None
    log_action(
        ActivityLog.Action.LOGIN_FAILED,
        username=username,
        ip_address=ip_address or None,
    )
