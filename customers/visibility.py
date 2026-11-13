"""Which customer fields a user may see. The single place for this rule."""

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

STAFF_FIELDS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "license_plate",
    "bank_name",
    "account_number",
    "referral",
)
ADMIN_ONLY_FIELDS: tuple[str, ...] = ("phone",)


def can_see_phone(user: AbstractBaseUser | AnonymousUser) -> bool:
    """Only admins ever see, search or export phone numbers."""
    return bool(user.is_authenticated and user.is_admin)


def visible_fields(user: AbstractBaseUser | AnonymousUser) -> tuple[str, ...]:
    """Customer fields this user may read and search."""
    if can_see_phone(user):
        return STAFF_FIELDS + ADMIN_ONLY_FIELDS
    return STAFF_FIELDS


def mask_account_number(account_number: str) -> str:
    """Show only the last 4 digits, for example '•••• 4567'."""
    return f"•••• {account_number[-4:]}"
