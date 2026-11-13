import pytest
from django.core.exceptions import ValidationError

from customers.models import DEFAULT_REFERRAL, normalize_referral


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


@pytest.mark.parametrize("field", ["phone", "account_number"])
def test_phone_and_account_number_must_be_digits(make_customer, field) -> None:
    customer = make_customer()
    setattr(customer, field, "08-1234 abc")

    with pytest.raises(ValidationError) as error:
        customer.full_clean()
    assert field in error.value.message_dict


def test_new_customer_is_visible_and_str_has_no_sensitive_data(make_customer) -> None:
    customer = make_customer()

    assert customer.is_hidden is False
    assert str(customer) == "ทดสอบ ตัวอย่าง"
    assert customer.phone not in str(customer)
    assert customer.account_number not in str(customer)
