"""Login, logout, default deny, lockout and login logging. All data is fake."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.permissions import admin_required
from audit.models import ActivityLog

pytestmark = pytest.mark.django_db

LOGIN = reverse("login")
LOGOUT = reverse("logout")
CUSTOMERS = reverse("customer_list")
PASSWORD = "correct-horse-battery"


@pytest.fixture
def nisa():
    return get_user_model().objects.create_user(
        username="nisa", password=PASSWORD, first_name="นิสา"
    )


def log_in(client, username="nisa", password=PASSWORD):
    return client.post(LOGIN, {"username": username, "password": password})


# --- Default deny ---------------------------------------------------------


def test_anonymous_user_is_sent_to_login(client) -> None:
    response = client.get(CUSTOMERS)

    assert response.status_code == 302
    assert response.url == f"{LOGIN}?next={CUSTOMERS}"


@pytest.mark.parametrize("name", ["login", "register", "register_thanks"])
def test_public_pages_need_no_login(client, name) -> None:
    assert client.get(reverse(name)).status_code == 200


def test_home_redirects_to_customers(client, staff) -> None:
    client.force_login(staff)

    response = client.get("/")

    assert response.status_code == 302
    assert response.url == CUSTOMERS


# --- Login and logout -----------------------------------------------------


def test_login_works_and_greets_by_first_name(client, nisa) -> None:
    response = log_in(client)

    assert response.status_code == 302
    assert response.url == CUSTOMERS
    assert "สวัสดี นิสา" in client.get(CUSTOMERS).text


def test_session_lasts_seven_days(client, nisa) -> None:
    log_in(client)

    assert client.cookies["sessionid"]["max-age"] == 7 * 24 * 60 * 60


def test_wrong_password_shows_an_error_and_does_not_log_in(client, nisa) -> None:
    response = log_in(client, password="wrong-password")

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert client.get(CUSTOMERS).status_code == 302


def test_deactivated_user_cannot_log_in(client, nisa) -> None:
    nisa.is_active = False
    nisa.save()

    log_in(client)

    assert client.get(CUSTOMERS).status_code == 302


def test_open_session_ends_when_the_user_is_deactivated(client, nisa) -> None:
    log_in(client)
    assert client.get(CUSTOMERS).status_code == 200

    nisa.is_active = False
    nisa.save()

    assert client.get(CUSTOMERS).status_code == 302


def test_logout_must_be_a_post(client, nisa) -> None:
    log_in(client)

    assert client.get(LOGOUT).status_code == 405
    assert client.get(CUSTOMERS).status_code == 200


def test_logout_ends_the_session(client, nisa) -> None:
    log_in(client)

    response = client.post(LOGOUT)

    assert response.status_code == 302
    assert response.url == LOGIN
    assert client.get(CUSTOMERS).status_code == 302


# --- Lockout --------------------------------------------------------------


def test_five_wrong_passwords_lock_the_account(client, nisa) -> None:
    for _ in range(4):
        assert log_in(client, password="wrong-password").status_code == 200

    fifth = log_in(client, password="wrong-password")
    assert fifth.status_code == 429
    assert "บัญชีถูกล็อกชั่วคราว" in fifth.text

    # Even the right password is refused while locked.
    assert log_in(client).status_code == 429
    assert client.get(CUSTOMERS).status_code == 302


def test_lockout_does_not_block_other_users(client, nisa, staff) -> None:
    staff.set_password(PASSWORD)
    staff.save()
    for _ in range(5):
        log_in(client, password="wrong-password")

    response = log_in(client, username="staff1")

    assert response.status_code == 302
    assert response.url == CUSTOMERS


def test_successful_login_resets_the_failure_count(client, nisa) -> None:
    for _ in range(4):
        log_in(client, password="wrong-password")
    log_in(client)
    client.post(LOGOUT)

    assert log_in(client, password="wrong-password").status_code == 200


# --- Activity log ---------------------------------------------------------


def test_login_writes_exactly_one_log_row(client, nisa) -> None:
    log_in(client)

    entry = ActivityLog.objects.get()
    assert entry.action == "login"
    assert entry.user == nisa
    assert entry.username == "nisa"
    assert entry.ip_address == "127.0.0.1"


def test_failed_login_is_logged_without_the_password(client, nisa) -> None:
    log_in(client, password="wrong-password")

    entry = ActivityLog.objects.get()
    assert entry.action == "login_failed"
    assert entry.user is None
    assert entry.username == "nisa"
    assert "wrong-password" not in str(entry.details)


# --- @admin_required ------------------------------------------------------


@admin_required
def admin_only_view(request):
    return HttpResponse("secret")


def test_admin_required_lets_admins_in(admin) -> None:
    request = RequestFactory().get("/admin-only/")
    request.user = admin

    assert admin_only_view(request).status_code == 200


def test_admin_required_returns_403_for_staff(staff) -> None:
    request = RequestFactory().get("/admin-only/")
    request.user = staff

    with pytest.raises(PermissionDenied):
        admin_only_view(request)


def test_admin_required_ignores_django_staff_and_superuser_flags(staff) -> None:
    staff.is_staff = True
    staff.is_superuser = True
    request = RequestFactory().get("/admin-only/")
    request.user = staff

    with pytest.raises(PermissionDenied):
        admin_only_view(request)


def test_admin_required_sends_anonymous_users_to_login() -> None:
    from django.contrib.auth.models import AnonymousUser

    request = RequestFactory().get("/admin-only/")
    request.user = AnonymousUser()

    response = admin_only_view(request)

    assert response.status_code == 302
    assert response.url.startswith(LOGIN)
