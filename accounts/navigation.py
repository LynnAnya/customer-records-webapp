"""The app menu, defined once. Sidebar and bottom tabs both render from it.

Hiding a menu item is a convenience only: every view still checks permissions.
"""

from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    icon: str
    admin_only: bool = False


# Add an item here when its page is built (staff, activity log, settings).
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(label="ลูกค้า", url_name="customer_list", icon="users"),
)


def nav_items(user: AbstractBaseUser | AnonymousUser) -> list[NavItem]:
    """Menu items this user may see. Staff never get admin-only items."""
    if not user.is_authenticated:
        return []
    return [item for item in NAV_ITEMS if not item.admin_only or user.is_admin]
