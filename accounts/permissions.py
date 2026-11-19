from collections.abc import Callable
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse


def admin_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Guard for admin-only views.

    Anonymous users go to the login page. Logged-in staff get 403.
    `is_admin` is the only flag checked; never `is_staff` or `is_superuser`.
    """

    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


# --- Who may act on which account (staff pages) ----------------------------
# Admins manage staff accounts only. They never edit, reset or (de)activate
# another admin; admins are created and managed from the server shell. An
# admin may still edit their own name and username.


def can_edit_account(actor, target) -> bool:
    """Change username, first name and last name."""
    return not target.is_admin or target.pk == actor.pk


def can_manage_account(actor, target) -> bool:
    """Set a new password, deactivate or reactivate."""
    return not target.is_admin
