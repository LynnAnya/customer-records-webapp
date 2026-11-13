from django.http import HttpRequest

from accounts.navigation import NavItem, nav_items


def navigation(request: HttpRequest) -> dict[str, list[NavItem]]:
    """Makes `nav_items` available in every template."""
    user = getattr(request, "user", None)
    return {"nav_items": nav_items(user) if user is not None else []}
