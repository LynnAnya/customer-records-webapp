"""Visitor address behind Render (Cloudflare in front) and on a laptop."""

import pytest
from django.test import RequestFactory

from audit.services import get_client_ip

PROXY = "10.0.0.5"  # what REMOTE_ADDR shows behind Render: the proxy


def request(**meta):
    return RequestFactory().get("/", REMOTE_ADDR=PROXY, **meta)


def test_live_uses_cloudflares_real_address(settings) -> None:
    settings.TRUST_CF_CONNECTING_IP = True

    assert get_client_ip(request(HTTP_CF_CONNECTING_IP="203.0.113.7")) == "203.0.113.7"
    assert get_client_ip(request(HTTP_CF_CONNECTING_IP="2001:db8::1")) == "2001:db8::1"


def test_live_ignores_the_fakeable_forwarded_for_header(settings) -> None:
    settings.TRUST_CF_CONNECTING_IP = True

    faked = request(
        HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7",
        HTTP_CF_CONNECTING_IP="203.0.113.7",
    )

    assert get_client_ip(faked) == "203.0.113.7"


@pytest.mark.parametrize("bad", ["", "not-an-ip", "1.2.3.4, 5.6.7.8", "<script>"])
def test_a_missing_or_broken_header_falls_back_to_the_connection(settings, bad) -> None:
    settings.TRUST_CF_CONNECTING_IP = True

    assert get_client_ip(request(HTTP_CF_CONNECTING_IP=bad)) == PROXY


def test_laptop_never_trusts_the_header(settings) -> None:
    settings.TRUST_CF_CONNECTING_IP = False

    assert get_client_ip(request(HTTP_CF_CONNECTING_IP="203.0.113.7")) == PROXY


@pytest.mark.django_db
def test_rate_limit_counts_each_real_visitor_separately(client, settings) -> None:
    """Behind the proxy two customers share REMOTE_ADDR but not their real IP."""
    from django.urls import reverse

    from customers.models import Customer

    settings.TRUST_CF_CONNECTING_IP = True
    settings.REGISTRATION_RATE_LIMIT_PER_HOUR = 1
    data = {
        "name": "ทดสอบ", "license_plate": "1กข 1", "phone": "0800000000",
        "bank_name": "ธนาคารทดสอบ", "account_number": "0001234567",
        "referral": "", "website": "",
    }  # fmt: skip
    url = reverse("register")

    def post(real_ip: str):
        return client.post(url, data, REMOTE_ADDR=PROXY, HTTP_CF_CONNECTING_IP=real_ip)

    first, second, again = post("203.0.113.1"), post("203.0.113.2"), post("203.0.113.1")

    assert (first.status_code, second.status_code, again.status_code) == (302, 302, 429)
    assert Customer.objects.count() == 2
