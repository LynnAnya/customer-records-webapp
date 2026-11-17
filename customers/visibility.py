"""Which customer fields a user may see. The single place for this rule."""

from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

if TYPE_CHECKING:
    from customers.models import Customer

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


def export_values(customer: "Customer") -> list[tuple[str, str]]:
    """(Thai label, value) pairs that leave the app in copy text, share text
    and PDF. The same for admins and staff.

    Decided 2026-11-17: no phone number in any export, for any role. The full
    account number is included, because staff need it to make the transfer.
    Copy text and PDF both build from this list, so a field cannot be added to
    one of them by accident.
    """
    return [
        ("ชื่อ", customer.full_name),
        ("ทะเบียนรถ", customer.license_plate),
        ("ธนาคาร", customer.bank_name),
        ("เลขที่บัญชี", customer.account_number),
    ]
