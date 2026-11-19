from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts import services
from accounts.forms import ThaiPasswordChangeForm
from accounts.models import User
from audit.services import get_client_ip


@require_POST
def set_theme(request: HttpRequest) -> HttpResponse:
    """Save the logged-in person's theme on their account (both roles).

    Not written to the activity log: a display preference, not data access.
    """
    theme = request.POST.get("theme", "")
    if theme not in User.Theme.values:
        return HttpResponseBadRequest()
    if request.user.theme != theme:
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    return HttpResponse(status=204)


@require_GET
def account(request: HttpRequest) -> HttpResponse:
    """Read-only page with the logged-in user's own account details."""
    return render(request, "accounts/account.html")


@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def password_change(request: HttpRequest) -> HttpResponse:
    """Change your own password (both roles). Asks for the current one first."""
    form = ThaiPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = services.change_own_password(form, get_client_ip(request))
        # Keep this browser logged in; other sessions of this user end.
        update_session_auth_hash(request, user)
        messages.success(request, "เปลี่ยนรหัสผ่านแล้ว")
        return redirect("account")
    context = {
        "form": form,
        "title": "เปลี่ยนรหัสผ่าน",
        "lead": "กรอกรหัสผ่านปัจจุบัน แล้วตั้งรหัสผ่านใหม่",
        "submit_label": "เปลี่ยนรหัสผ่าน",
        "back_url_name": "account",
    }
    return render(request, "accounts/form_page.html", context)
