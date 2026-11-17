"""Staff management pages. Every view here is guarded by @admin_required."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts import services
from accounts.forms import StaffCreateForm
from accounts.permissions import admin_required
from audit.services import get_client_ip


@admin_required
@require_GET
def staff_list(request: HttpRequest) -> HttpResponse:
    users = get_user_model().objects.order_by("-is_active", "-is_admin", "username")
    return render(request, "accounts/staff_list.html", {"users": users})


@admin_required
@require_http_methods(["GET", "POST"])
def staff_create(request: HttpRequest) -> HttpResponse:
    form = StaffCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = services.create_staff(form, request.user, get_client_ip(request))
        messages.success(request, f"เพิ่มพนักงาน {user.get_username()} แล้ว")
        return redirect("staff_list")
    context = {
        "form": form,
        "title": "เพิ่มพนักงาน",
        "lead": "ตั้งชื่อผู้ใช้และรหัสผ่านให้พนักงาน แล้วแจ้งให้พนักงานทราบด้วยตนเอง",
        "submit_label": "เพิ่มพนักงาน",
        "back_url_name": "staff_list",
    }
    return render(request, "accounts/form_page.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def staff_reset_password(request: HttpRequest, pk: int) -> HttpResponse:
    target = get_object_or_404(get_user_model(), pk=pk)
    if target.pk == request.user.pk:
        # Your own password needs your current password: use the normal page.
        return redirect("password_change")

    form = SetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.reset_password(form, request.user, get_client_ip(request))
        messages.success(request, f"ตั้งรหัสผ่านใหม่ให้ {target.get_username()} แล้ว")
        return redirect("staff_list")
    context = {
        "form": form,
        "title": "ตั้งรหัสผ่านใหม่",
        "lead": f"บัญชี {target.get_username()} ({target.get_full_name() or '-'})",
        "submit_label": "บันทึกรหัสผ่านใหม่",
        "back_url_name": "staff_list",
    }
    return render(request, "accounts/form_page.html", context)


@admin_required
@require_POST
def staff_set_active(request: HttpRequest, pk: int) -> HttpResponse:
    get_object_or_404(get_user_model(), pk=pk)
    active = request.POST.get("active") == "1"
    try:
        target = services.set_active(request.user, pk, active, get_client_ip(request))
    except services.StaffRuleError as error:
        messages.error(request, str(error))
    else:
        verb = "เปิดใช้งาน" if active else "ปิดใช้งาน"
        messages.success(request, f"{verb}บัญชี {target.get_username()} แล้ว")
    return redirect("staff_list")
