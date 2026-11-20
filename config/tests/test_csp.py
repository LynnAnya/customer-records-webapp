"""Content-Security-Policy header."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_live_enforces_a_policy_that_only_allows_this_site(client, settings) -> None:
    settings.SECURE_CSP = settings.CONTENT_SECURITY_POLICY
    settings.SECURE_CSP_REPORT_ONLY = {}

    policy = client.get(reverse("login"))["Content-Security-Policy"]

    assert "default-src 'self'" in policy
    assert "script-src 'self' 'unsafe-eval'" in policy
    assert "'unsafe-inline'" not in policy  # no inline scripts or styles anywhere
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy


def test_pages_have_no_inline_scripts_or_styles(client, admin, make_customer) -> None:
    make_customer()
    client.force_login(admin)

    for url in ("customer_list", "activity_log", "staff_list", "account", "login"):
        page = client.get(reverse(url)).text
        assert "<script>" not in page and "<style" not in page, url
        assert ' style="' not in page, url
        assert ' onclick="' not in page, url
