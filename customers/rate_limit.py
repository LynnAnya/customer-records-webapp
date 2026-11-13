"""Rate limit for the public registration form, counted on the server per IP."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from customers.models import RegistrationAttempt

WINDOW = timedelta(hours=1)
KEEP_ROWS_FOR = timedelta(days=1)


def is_rate_limited(ip_address: str) -> bool:
    """True when this IP already saved the allowed number of forms this hour."""
    recent = RegistrationAttempt.objects.filter(
        ip_address=ip_address, created_at__gte=timezone.now() - WINDOW
    ).count()
    return recent >= settings.REGISTRATION_RATE_LIMIT_PER_HOUR


def record_attempt(ip_address: str) -> None:
    """Count one saved registration and drop rows too old to matter."""
    RegistrationAttempt.objects.filter(
        created_at__lt=timezone.now() - KEEP_ROWS_FOR
    ).delete()
    RegistrationAttempt.objects.create(ip_address=ip_address)
