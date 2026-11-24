"""Admin-only customer pages. Every view here is guarded by @admin_required."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import admin_required
from audit.services import get_client_ip
from customers import services
from customers.filters import parse_selected_ids
from customers.forms import AdminCustomerForm
from customers.models import Customer
from customers.queries import account_duplicates, phone_duplicates, visible_customers


def _back_url(request: HttpRequest) -> str:
    """Where the admin came from (keeps search and filters).

    `next` comes from the browser, so only a URL on this site is accepted.
    Templates use this value too; never print the raw `next` into a link.
    """
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse("customer_list")


def _back_to_list(request: HttpRequest) -> HttpResponse:
    return redirect(_back_url(request))


def _warn_about_duplicates(request: HttpRequest, customer: Customer) -> None:
    """Duplicate phones and account numbers are allowed, but the admin is told.

    Names only: never the phone or account number itself.
    """
    checks = (
        ("เบอร์โทร", phone_duplicates(customer)),
        ("เลขที่บัญชี", account_duplicates(customer)),
    )
    for label, duplicates in checks:
        others = [other.name for other in duplicates[:5]]
        if others:
            messages.warning(
                request,
                f"{label}ของ {customer.name} ซ้ำกับลูกค้ารายอื่น: {', '.join(others)}",
            )


@admin_required
@require_http_methods(["GET", "POST"])
def customer_create(request: HttpRequest) -> HttpResponse:
    form = AdminCustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = services.create_customer(form, request.user, get_client_ip(request))
        messages.success(request, f"เพิ่มลูกค้า {customer.name} แล้ว")
        _warn_about_duplicates(request, customer)
        return _back_to_list(request)
    context = {"form": form, "customer": None, "back_url": _back_url(request)}
    return render(request, "customers/form.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def customer_edit(request: HttpRequest, pk: int) -> HttpResponse:
    customer = get_object_or_404(visible_customers(request.user), pk=pk)
    form = AdminCustomerForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        customer = services.update_customer(form, request.user, get_client_ip(request))
        messages.success(request, f"บันทึกข้อมูล {customer.name} แล้ว")
        _warn_about_duplicates(request, customer)
        return _back_to_list(request)
    context = {
        "form": form,
        "customer": customer,
        "duplicates": phone_duplicates(customer)[:5],
        "account_duplicates": account_duplicates(customer)[:5],
        "back_url": _back_url(request),
    }
    return render(request, "customers/form.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def customer_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET shows the confirmation page. Only POST deletes."""
    customer = get_object_or_404(visible_customers(request.user), pk=pk)
    if request.method == "POST":
        name = customer.name
        services.delete_customer(customer, request.user, get_client_ip(request))
        messages.success(request, f"ลบลูกค้า {name} แล้ว")
        return _back_to_list(request)
    context = {"customer": customer, "back_url": _back_url(request)}
    return render(request, "customers/confirm_delete.html", context)


# The word an admin types to confirm deleting several customers at once.
BULK_DELETE_WORD = "ลบ"


@admin_required
@require_POST
def customer_bulk_delete(request: HttpRequest) -> HttpResponse:
    """Delete every ticked customer, after the admin types the confirm word.

    The first POST (from the selection bar) shows the confirmation page. The
    second POST, with the typed word, deletes. IDs are re-checked every time.
    """
    ids = parse_selected_ids(request.POST.get("ids"))
    customers = list(
        visible_customers(request.user).filter(pk__in=ids).order_by("name", "pk")
    )
    if not customers:
        messages.info(request, "ไม่มีรายการที่ต้องลบ")
        return _back_to_list(request)

    typed = request.POST.get("confirm")
    error = ""
    if typed is not None:
        if typed.strip() == BULK_DELETE_WORD:
            deleted = services.delete_customers(
                request.user, [customer.pk for customer in customers],
                get_client_ip(request),
            )  # fmt: skip
            messages.success(request, f"ลบลูกค้า {deleted} รายแล้ว")
            return _back_to_list(request)
        error = f"กรุณาพิมพ์คำว่า “{BULK_DELETE_WORD}” ให้ถูกต้องเพื่อยืนยัน"

    context = {
        "customers": customers,
        "ids": ",".join(str(customer.pk) for customer in customers),
        "confirm_word": BULK_DELETE_WORD,
        "error": error,
        "back_url": _back_url(request),
    }
    return render(request, "customers/confirm_bulk_delete.html", context)


@admin_required
@require_POST
def customer_set_hidden(request: HttpRequest) -> HttpResponse:
    """Hide or unhide one customer or every ticked customer."""
    ids = parse_selected_ids(request.POST.get("ids"))
    hidden = request.POST.get("hidden") == "1"
    changed = services.set_hidden(request.user, ids, hidden, get_client_ip(request))
    if changed:
        verb = "ซ่อน" if hidden else "ยกเลิกการซ่อน"
        messages.success(request, f"{verb}ลูกค้า {changed} รายแล้ว")
    else:
        messages.info(request, "ไม่มีรายการที่ต้องเปลี่ยนแปลง")
    return _back_to_list(request)
