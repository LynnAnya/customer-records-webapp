"""Public QR registration form. All data here is fake."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer, RegistrationAttempt

pytestmark = pytest.mark.django_db

REGISTER = reverse("register")
THANKS = reverse("register_thanks")


def valid_data(**overrides) -> dict[str, str]:
    data = {
        "first_name": "ทดสอบ",
        "last_name": "ตัวอย่าง",
        "license_plate": "1กข 1234",
        "phone": "0800000000",
        "bank_name": "ธนาคารทดสอบ",
        "account_number": "0001234567",
        "referral": "",
        "consent": "on",
        "website": "",
    }
    data.update(overrides)
    return data


def test_form_page_is_public(client) -> None:
    response = client.get(REGISTER)

    assert response.status_code == 200
    assert "ลงทะเบียนลูกค้า" in response.text


def test_valid_form_saves_a_qr_customer_and_redirects(client) -> None:
    response = client.post(REGISTER, valid_data())

    assert response.status_code == 302
    assert response.url == THANKS
    customer = Customer.objects.get()
    assert customer.created_by == Customer.CreatedBy.QR_CODE
    assert customer.consent_at is not None
    assert customer.is_hidden is False
    assert customer.referral == "บริษัท"


def test_referral_is_kept_when_given(client) -> None:
    client.post(REGISTER, valid_data(referral="  คุณ   สมศรี "))

    assert Customer.objects.get().referral == "คุณ สมศรี"


def test_spaces_and_dashes_are_removed_from_numbers(client) -> None:
    data = valid_data(phone="080-000 0000", account_number="000-1-23456-7")
    client.post(REGISTER, data)

    customer = Customer.objects.get()
    assert customer.phone == "0800000000"
    assert customer.account_number == "0001234567"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone", "080000000"),  # 9 digits
        ("phone", "08000000000"),  # 11 digits
        ("phone", "1800000000"),  # does not start with 0
        ("phone", "08000abcde"),
        ("account_number", "12ab34"),
        ("account_number", "1" * 21),
        ("first_name", ""),
        ("last_name", ""),
        ("license_plate", ""),
        ("bank_name", ""),
        ("consent", ""),
    ],
)
def test_invalid_input_is_rejected_with_an_error(client, field, value) -> None:
    response = client.post(REGISTER, valid_data(**{field: value}))

    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert Customer.objects.count() == 0


def test_honeypot_submission_is_dropped_but_looks_successful(client) -> None:
    response = client.post(REGISTER, valid_data(website="http://spam.example"))

    assert response.status_code == 302
    assert response.url == THANKS
    assert Customer.objects.count() == 0


def test_rate_limit_blocks_extra_submissions(client, settings) -> None:
    settings.REGISTRATION_RATE_LIMIT_PER_HOUR = 2
    client.post(REGISTER, valid_data())
    client.post(REGISTER, valid_data())

    response = client.post(REGISTER, valid_data())

    assert response.status_code == 429
    assert Customer.objects.count() == 2


def test_rate_limit_is_per_ip_address(client, settings) -> None:
    settings.REGISTRATION_RATE_LIMIT_PER_HOUR = 1
    client.post(REGISTER, valid_data())

    response = client.post(REGISTER, valid_data(), REMOTE_ADDR="10.0.0.9")

    assert response.status_code == 302
    assert Customer.objects.count() == 2


def test_rate_limit_forgets_attempts_older_than_an_hour(client, settings) -> None:
    settings.REGISTRATION_RATE_LIMIT_PER_HOUR = 1
    client.post(REGISTER, valid_data())
    RegistrationAttempt.objects.update(created_at=timezone.now() - timedelta(hours=2))

    response = client.post(REGISTER, valid_data())

    assert response.status_code == 302
    assert Customer.objects.count() == 2


def test_failed_validation_does_not_use_up_the_rate_limit(client) -> None:
    client.post(REGISTER, valid_data(phone="123"))

    assert RegistrationAttempt.objects.count() == 0


def test_thank_you_page_shows_no_submitted_data(client) -> None:
    response = client.post(REGISTER, valid_data(), follow=True)

    assert response.status_code == 200
    for value in ("0800000000", "0001234567", "ทดสอบ", "1กข 1234"):
        assert value not in response.text


def test_post_without_csrf_token_is_rejected() -> None:
    strict_client = Client(enforce_csrf_checks=True)

    response = strict_client.post(REGISTER, valid_data())

    assert response.status_code == 403
    assert Customer.objects.count() == 0


def test_other_http_methods_are_not_allowed(client) -> None:
    assert client.delete(REGISTER).status_code == 405
    assert client.post(THANKS).status_code == 405


def test_error_messages_are_friendly_thai(client) -> None:
    response = client.post(REGISTER, valid_data(first_name="", consent=""))

    errors = response.context["form"].errors
    assert errors["first_name"] == ["กรุณากรอกข้อมูลในช่องนี้"]
    assert errors["consent"] == ["กรุณากดยินยอมก่อนส่งข้อมูล"]
