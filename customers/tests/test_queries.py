from django.contrib.auth.models import AnonymousUser

from customers.queries import visible_customers


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
