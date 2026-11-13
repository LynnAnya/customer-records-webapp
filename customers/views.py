from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from audit.services import get_client_ip
from customers.forms import PublicRegistrationForm
from customers.models import Customer
from customers.rate_limit import is_rate_limited, record_attempt


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


@require_GET
def customer_list(request: HttpRequest) -> HttpResponse:
    """Temporary landing page after login. The real customers page is step 5."""
    return render(request, "customers/home.html")
