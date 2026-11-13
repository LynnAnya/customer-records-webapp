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
