import pytest
from django.core.exceptions import ValidationError

from customers.models import DEFAULT_REFERRAL, MISSING, normalize_referral


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_referral_becomes_default(make_customer, blank) -> None:
    customer = make_customer(referral=blank)

    customer.refresh_from_db()
    assert customer.referral == DEFAULT_REFERRAL == "บริษัท"


def test_referral_spaces_are_trimmed_and_collapsed(make_customer) -> None:
    customer = make_customer(referral="  คุณ   สมศรี  ")

    assert customer.referral == "คุณ สมศรี"
    assert normalize_referral("A   B") == "A B"


def test_account_number_keeps_leading_zeros(make_customer) -> None:
    customer = make_customer(account_number="0001234567")

    customer.refresh_from_db()
    assert customer.account_number == "0001234567"


def test_account_number_must_be_digits_or_a_dash(make_customer) -> None:
    customer = make_customer()
    customer.account_number = "08-1234 abc"

    with pytest.raises(ValidationError) as error:
        customer.full_clean()
    assert "account_number" in error.value.message_dict

    customer.account_number = MISSING
    customer.full_clean()


def test_phone_is_free_text(make_customer) -> None:
    customer = make_customer(phone="ใช้เบอร์ John")

    customer.full_clean()


def test_new_customer_is_visible_and_str_has_no_sensitive_data(make_customer) -> None:
    customer = make_customer()

    assert customer.is_hidden is False
    assert str(customer) == "ทดสอบ ตัวอย่าง"
    assert customer.phone not in str(customer)
    assert customer.account_number not in str(customer)
