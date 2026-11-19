"""Staff management pages. Every view here is guarded by @admin_required."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts import services
from accounts.forms import StaffCreateForm, StaffEditForm, ThaiSetPasswordForm
from accounts.permissions import (
    admin_required,
    can_edit_account,
    can_manage_account,
)
from audit.services import get_client_ip


@admin_required
@require_GET
def staff_list(request: HttpRequest) -> HttpResponse:
    users = list(
        get_user_model().objects.order_by("-is_active", "-is_admin", "username")
    )
    for person in users:
        person.can_edit = can_edit_account(request.user, person)
        person.can_manage = can_manage_account(request.user, person)
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
def staff_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Change an account's username, first name and last name."""
    target = get_object_or_404(get_user_model(), pk=pk)
    if not can_edit_account(request.user, target):
        raise PermissionDenied
    form = StaffEditForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        if services.edit_staff(form, request.user, get_client_ip(request)):
            messages.success(request, f"บันทึกข้อมูลบัญชี {target.get_username()} แล้ว")
        else:
            messages.info(request, "ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return redirect("staff_list")
    context = {
        "form": form,
        "title": "แก้ไขข้อมูลบัญชี",
        "lead": "เปลี่ยนชื่อผู้ใช้ ชื่อ หรือนามสกุล ถ้าเปลี่ยนชื่อผู้ใช้ ต้องแจ้งเจ้าของบัญชีด้วย",
        "submit_label": "บันทึก",
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
    if not can_manage_account(request.user, target):
        raise PermissionDenied

    form = ThaiSetPasswordForm(target, request.POST or None)
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
    target = get_object_or_404(get_user_model(), pk=pk)
    if not can_manage_account(request.user, target):
        raise PermissionDenied
    active = request.POST.get("active") == "1"
    try:
        target = services.set_active(request.user, pk, active, get_client_ip(request))
    except services.StaffRuleError as error:
        messages.error(request, str(error))
    else:
        verb = "เปิดใช้งาน" if active else "ปิดใช้งาน"
        messages.success(request, f"{verb}บัญชี {target.get_username()} แล้ว")
    return redirect("staff_list")
