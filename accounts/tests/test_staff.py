"""Staff management and password change. All data is fake."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts import services
from accounts.navigation import nav_items
from audit.models import ActivityLog

User = get_user_model()
LOGIN = reverse("login")
LIST = reverse("staff_list")
CREATE = reverse("staff_create")
CHANGE = reverse("password_change")
CUSTOMERS = reverse("customer_list")
GOOD = "correct-horse-battery"
NEW = "another-good-secret-9"


def reset_url(user) -> str:
    return reverse("staff_reset_password", args=[user.pk])


def active_url(user) -> str:
    return reverse("staff_set_active", args=[user.pk])


def logged():
    return ActivityLog.objects.exclude(action=ActivityLog.Action.LOGIN)


def new_staff(**overrides) -> dict[str, str]:
    data = {
        "username": "mali",
        "first_name": "มะลิ",
        "last_name": "ตัวอย่าง",
        "password1": GOOD,
        "password2": GOOD,
    }
    data.update(overrides)
    return data


@pytest.fixture
def second_admin(db):
    return User.objects.create_user(username="admin2", password=GOOD, is_admin=True)


# --- Permission matrix ----------------------------------------------------


def staff_admin_urls(target) -> list[tuple[str, str]]:
    return [
        ("get", LIST),
        ("get", CREATE),
        ("post", CREATE),
        ("get", reset_url(target)),
        ("post", reset_url(target)),
        ("post", active_url(target)),
    ]


def test_staff_get_403_everywhere_and_nothing_changes(client, staff, admin) -> None:
    client.force_login(staff)

    for method, url in staff_admin_urls(admin):
        data = new_staff() | {"new_password1": NEW, "new_password2": NEW, "active": "0"}
        assert getattr(client, method)(url, data).status_code == 403, (method, url)

    admin.refresh_from_db()
    assert admin.is_active is True
    assert User.objects.count() == 2
    assert logged().count() == 0


def test_anonymous_users_are_sent_to_login(client, admin) -> None:
    for method, url in [*staff_admin_urls(admin), ("get", CHANGE), ("post", CHANGE)]:
        response = getattr(client, method)(url)
        assert response.status_code == 302, (method, url)
        assert response.url.startswith(LOGIN), (method, url)


def test_staff_menu_item_is_for_admins_only(client, admin, staff) -> None:
    assert "staff_list" in [item.url_name for item in nav_items(admin)]
    assert "staff_list" not in [item.url_name for item in nav_items(staff)]

    client.force_login(staff)
    assert LIST not in client.get(CUSTOMERS).text


def test_phone_tab_bar_has_at_most_five_items(admin, staff) -> None:
    # Tabs = menu items marked in_tabs + ตั้งค่า + ออก.
    for user in (admin, staff):
        assert len([item for item in nav_items(user) if item.in_tabs]) + 2 <= 5


# --- Staff list -----------------------------------------------------------


def test_list_shows_accounts_but_never_passwords(client, admin, staff) -> None:
    client.force_login(admin)

    page = client.get(LIST).text

    assert "staff1" in page and "admin1" in page
    assert "ใช้งานอยู่" in page
    assert staff.password not in page
    assert "pbkdf2" not in page and "argon2" not in page


# --- Add staff ------------------------------------------------------------


def test_admin_adds_a_staff_account(client, admin) -> None:
    client.force_login(admin)

    response = client.post(CREATE, new_staff())

    assert response.status_code == 302
    created = User.objects.get(username="mali")
    assert (created.is_admin, created.is_staff, created.is_superuser) == (
        False,
        False,
        False,
    )
    assert created.is_active is True
    assert created.check_password(GOOD)
    assert created.password != GOOD


def test_add_staff_cannot_create_an_admin(client, admin) -> None:
    client.force_login(admin)

    client.post(CREATE, new_staff(is_admin="on", is_staff="on", is_superuser="on"))

    created = User.objects.get(username="mali")
    assert (created.is_admin, created.is_staff, created.is_superuser) == (
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"password1": "12345678", "password2": "12345678"},  # all numbers
        {"password1": "short1", "password2": "short1"},  # too short
        {"password2": "does-not-match-1"},
        {"username": "staff1"},  # already taken
        {"first_name": ""},
    ],
)
def test_add_staff_validation(client, admin, staff, bad) -> None:
    client.force_login(admin)

    response = client.post(CREATE, new_staff(**bad))

    assert response.status_code == 200
    assert response.context["form"].errors
    assert not User.objects.filter(username="mali").exists()
    assert logged().count() == 0


def test_new_staff_can_log_in_and_sees_no_admin_pages(client, admin) -> None:
    client.force_login(admin)
    client.post(CREATE, new_staff())
    client.post(reverse("logout"))

    client.post(LOGIN, {"username": "mali", "password": GOOD})

    assert client.get(CUSTOMERS).status_code == 200
    assert client.get(LIST).status_code == 403


# --- Reset password -------------------------------------------------------


def test_admin_resets_a_password(client, admin, staff) -> None:
    client.force_login(admin)

    response = client.post(
        reset_url(staff), {"new_password1": NEW, "new_password2": NEW}
    )

    assert response.status_code == 302
    staff.refresh_from_db()
    assert staff.check_password(NEW)


def test_reset_ends_the_other_persons_open_session(client, admin, staff) -> None:
    from django.test import Client

    staff.set_password(GOOD)
    staff.save()
    staff_browser = Client()
    staff_browser.post(LOGIN, {"username": "staff1", "password": GOOD})
    assert staff_browser.get(CUSTOMERS).status_code == 200

    client.force_login(admin)
    client.post(reset_url(staff), {"new_password1": NEW, "new_password2": NEW})

    assert staff_browser.get(CUSTOMERS).status_code == 302


def test_reset_uses_the_password_rules(client, admin, staff) -> None:
    client.force_login(admin)
    old_hash = staff.password

    response = client.post(
        reset_url(staff), {"new_password1": "12345678", "new_password2": "12345678"}
    )

    assert response.status_code == 200
    staff.refresh_from_db()
    assert staff.password == old_hash
    assert logged().count() == 0


def test_resetting_yourself_goes_to_the_change_password_page(client, admin) -> None:
    client.force_login(admin)
    old_hash = admin.password

    response = client.post(
        reset_url(admin), {"new_password1": NEW, "new_password2": NEW}
    )

    assert response.status_code == 302
    assert response.url == CHANGE
    admin.refresh_from_db()
    assert admin.password == old_hash


# --- Deactivate / reactivate ----------------------------------------------


def test_deactivate_and_reactivate(client, admin, staff) -> None:
    client.force_login(admin)

    client.post(active_url(staff), {"active": "0"})
    staff.refresh_from_db()
    assert staff.is_active is False
    assert User.objects.filter(pk=staff.pk).exists()  # never deleted

    client.post(active_url(staff), {"active": "1"})
    staff.refresh_from_db()
    assert staff.is_active is True


def test_deactivate_must_be_a_post(client, admin, staff) -> None:
    client.force_login(admin)

    assert client.get(active_url(staff), {"active": "0"}).status_code == 405
    staff.refresh_from_db()
    assert staff.is_active is True


def test_deactivated_user_cannot_log_in_and_open_session_ends(
    client, admin, staff
) -> None:
    from django.test import Client

    staff.set_password(GOOD)
    staff.save()
    staff_browser = Client()
    staff_browser.post(LOGIN, {"username": "staff1", "password": GOOD})

    client.force_login(admin)
    client.post(active_url(staff), {"active": "0"})

    assert staff_browser.get(CUSTOMERS).status_code == 302
    fresh = Client()
    fresh.post(LOGIN, {"username": "staff1", "password": GOOD})
    assert fresh.get(CUSTOMERS).status_code == 302


def test_admin_cannot_deactivate_themselves(client, admin, second_admin) -> None:
    client.force_login(admin)

    client.post(active_url(admin), {"active": "0"})

    admin.refresh_from_db()
    assert admin.is_active is True
    assert logged().count() == 0


def test_last_active_admin_can_never_be_deactivated(admin, second_admin) -> None:
    # admin deactivates second_admin: fine, one admin is left.
    services.set_active(admin, second_admin.pk, False, None)

    # Now nobody may deactivate the last one, whoever asks.
    with pytest.raises(services.StaffRuleError):
        services.set_active(second_admin, admin.pk, False, None)

    admin.refresh_from_db()
    assert admin.is_active is True


def test_another_admin_can_be_deactivated_when_one_remains(
    client, admin, second_admin
) -> None:
    client.force_login(admin)

    client.post(active_url(second_admin), {"active": "0"})

    second_admin.refresh_from_db()
    assert second_admin.is_active is False


# --- Change my own password -----------------------------------------------


@pytest.fixture
def nisa(db):
    return User.objects.create_user(username="nisa", password=GOOD, first_name="นิสา")


def change(client, old=GOOD, new=NEW):
    data = {"old_password": old, "new_password1": new, "new_password2": new}
    return client.post(CHANGE, data)


def test_staff_can_change_their_own_password_and_stay_logged_in(client, nisa) -> None:
    client.post(LOGIN, {"username": "nisa", "password": GOOD})

    response = change(client)

    assert response.status_code == 302
    nisa.refresh_from_db()
    assert nisa.check_password(NEW)
    assert client.get(CUSTOMERS).status_code == 200


def test_change_password_needs_the_current_password(client, nisa) -> None:
    client.post(LOGIN, {"username": "nisa", "password": GOOD})

    response = change(client, old="wrong-current-pass")

    assert response.status_code == 200
    nisa.refresh_from_db()
    assert nisa.check_password(GOOD)
    assert logged().count() == 0


def test_password_change_is_never_forced(client, admin) -> None:
    client.force_login(admin)
    client.post(CREATE, new_staff())
    client.post(reverse("logout"))

    response = client.post(LOGIN, {"username": "mali", "password": GOOD})

    assert response.url == CUSTOMERS


# --- Activity log ---------------------------------------------------------


def test_each_staff_action_writes_one_row_without_passwords(
    client, admin, staff
) -> None:
    client.force_login(admin)

    steps = [
        ("staff_created", "mali", lambda: client.post(CREATE, new_staff())),
        (
            "staff_password_reset",
            "staff1",
            lambda: client.post(
                reset_url(staff), {"new_password1": NEW, "new_password2": NEW}
            ),
        ),
        (
            "staff_deactivated",
            "staff1",
            lambda: client.post(active_url(staff), {"active": "0"}),
        ),
        (
            "staff_reactivated",
            "staff1",
            lambda: client.post(active_url(staff), {"active": "1"}),
        ),
    ]
    for count, (action, target, run) in enumerate(steps, start=1):
        run()
        assert logged().count() == count, action
        entry = logged().latest("id")
        assert entry.action == action
        assert entry.user == admin
        assert entry.details == {"target_username": target}
        assert GOOD not in str(entry.details) and NEW not in str(entry.details)


def test_own_password_change_writes_one_row(client, nisa) -> None:
    client.post(LOGIN, {"username": "nisa", "password": GOOD})

    change(client)

    entry = logged().get()
    assert entry.action == "password_changed"
    assert entry.user == nisa
    assert entry.details == {}


def test_repeating_a_deactivation_logs_nothing_new(client, admin, staff) -> None:
    client.force_login(admin)
    client.post(active_url(staff), {"active": "0"})

    client.post(active_url(staff), {"active": "0"})

    assert logged().count() == 1
