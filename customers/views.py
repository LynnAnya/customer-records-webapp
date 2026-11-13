from urllib.parse import urlencode

from django.contrib.auth.decorators import login_not_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from audit.services import get_client_ip
from customers.filters import parse_filters, parse_selected_ids, referral_choices
from customers.forms import PublicRegistrationForm
from customers.models import Customer
from customers.queries import (
    DEFAULT_SORT,
    clean_sort,
    pinned_customers,
    search_customers,
    visible_customers,
)
from customers.rate_limit import is_rate_limited, record_attempt
from customers.visibility import can_see_phone

PAGE_SIZE = 25

# "Added by" filter: (stored value, Thai label).
SOURCE_OPTIONS = [
    (Customer.CreatedBy.QR_CODE.value, "ลงทะเบียนผ่าน QR code"),
    (Customer.CreatedBy.ADMIN.value, "ผู้ดูแลระบบเพิ่ม"),
    (Customer.CreatedBy.EXCEL.value, "นำเข้าจาก Excel"),
]

# Sort dropdown: (key, Thai label). Keys must exist in customers.queries.SORTS.
SORT_OPTIONS = [
    ("newest", "ใหม่ล่าสุด"),
    ("oldest", "เก่าที่สุด"),
    ("name_az", "ชื่อ ก-ฮ"),
    ("name_za", "ชื่อ ฮ-ก"),
    ("bank_az", "ธนาคาร ก-ฮ"),
    ("bank_za", "ธนาคาร ฮ-ก"),
]


@login_not_required
@require_http_methods(["GET", "POST"])
def register(request: HttpRequest) -> HttpResponse:
    """Public QR form. Write-only: it never shows stored data."""
    if request.method == "GET":
        return render(
            request, "customers/register.html", {"form": PublicRegistrationForm()}
        )

    form = PublicRegistrationForm(request.POST)
    ip_address = get_client_ip(request)

    if is_rate_limited(ip_address):
        context = {"form": form, "rate_limited": True}
        return render(request, "customers/register.html", context, status=429)

    if not form.is_valid():
        return render(request, "customers/register.html", {"form": form})

    # Bots get the same thank-you page, so they cannot tell they were dropped.
    if not form.is_bot():
        customer = form.save(commit=False)
        customer.created_by = Customer.CreatedBy.QR_CODE
        customer.consent_at = timezone.now()
        customer.save()
        record_attempt(ip_address)

    return redirect("register_thanks")


@login_not_required
@require_GET
def register_thanks(request: HttpRequest) -> HttpResponse:
    return render(request, "customers/register_thanks.html")


def _table_context(request: HttpRequest) -> dict:
    """Read search, sort, filters, page and ticked IDs from the URL."""
    user = request.user
    query = request.GET.get("q", "").strip()
    sort = clean_sort(request.GET.get("sort"))
    filters = parse_filters(request.GET, user)

    # Ticked rows come first, in tick order, and are left out of the results.
    selected_ids = parse_selected_ids(request.GET.get("selected"))
    pinned, dropped_ids = pinned_customers(user, selected_ids)

    results = search_customers(user, query, sort, filters)
    unpinned = results.exclude(pk__in=[customer.pk for customer in pinned])
    page = Paginator(unpinned, PAGE_SIZE).get_page(request.GET.get("page"))

    # Query string that keeps the current search, sort and filters in the URL.
    params = {}
    if query:
        params["q"] = query
    if sort != DEFAULT_SORT:
        params["sort"] = sort
    params.update(filters.as_params())
    return {
        "page": page,
        "pinned": pinned,
        "dropped_ids": ",".join(str(pk) for pk in dropped_ids),
        "total_count": results.count(),
        "query": query,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "filters": filters,
        "source_options": SOURCE_OPTIONS,
        "referral_options": referral_choices(visible_customers(user)),
        "state_query": urlencode(params),
        "show_phone": can_see_phone(user),
        "is_admin": user.is_admin,
    }


@require_GET
def customer_list(request: HttpRequest) -> HttpResponse:
    """The main page: greeting, search, sort and the customers table."""
    return render(request, "customers/list.html", _table_context(request))


@require_GET
def customer_table(request: HttpRequest) -> HttpResponse:
    """Only the table, for HTMX to swap in after a search, sort or page change."""
    context = _table_context(request)
    response = render(request, "customers/list.html#table", context)
    # Keep the address bar on the full page, so reload and bookmarks work.
    page_params = context["state_query"]
    if context["page"].number > 1:
        page_params = f"{page_params}&page={context['page'].number}".lstrip("&")
    response["HX-Push-Url"] = f"{reverse('customer_list')}?{page_params}".rstrip("?")
    return response
