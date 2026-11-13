from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def account(request: HttpRequest) -> HttpResponse:
    """Read-only page with the logged-in user's own account details."""
    return render(request, "accounts/account.html")
