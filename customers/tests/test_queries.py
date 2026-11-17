from django.contrib.auth.models import AnonymousUser

from customers.models import MISSING
from customers.queries import phone_duplicates, search_customers, visible_customers
from customers.visibility import mask_account_number


def test_admin_sees_hidden_and_visible_customers(admin, make_customer) -> None:
    shown = make_customer()
    hidden = make_customer(is_hidden=True)

    assert set(visible_customers(admin)) == {shown, hidden}


def test_staff_never_get_hidden_customers(staff, make_customer) -> None:
    shown = make_customer()
    hidden = make_customer(is_hidden=True)

    assert list(visible_customers(staff)) == [shown]
    assert not visible_customers(staff).filter(pk=hidden.pk).exists()


def test_anonymous_user_gets_nothing(make_customer) -> None:
    make_customer()

    assert not visible_customers(AnonymousUser()).exists()


def test_deactivated_user_gets_nothing(admin, make_customer) -> None:
    make_customer()
    admin.is_active = False

    assert not visible_customers(admin).exists()


def test_missing_phones_are_never_duplicates(admin, make_customer) -> None:
    first = make_customer(phone=MISSING)
    make_customer(phone=MISSING)

    flagged = search_customers(admin).get(pk=first.pk)

    assert flagged.has_duplicate_phone is False
    assert not phone_duplicates(first).exists()


def test_a_missing_account_number_is_shown_as_a_dash() -> None:
    assert mask_account_number(MISSING) == "-"
    assert mask_account_number("0001234567") == "•••• 4567"
