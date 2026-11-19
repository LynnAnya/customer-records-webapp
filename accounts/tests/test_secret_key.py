"""SECRET_KEY: what it protects in this app, and that it never leaks.

Django stamps each login session with a value built from SECRET_KEY and the
user's password hash, and checks that stamp on every request.
"""

from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse

from audit.models import ActivityLog

CUSTOMERS = reverse("customer_list")
LOGIN = reverse("login")
NEW_KEY = "a-completely-different-test-key-" + "x" * 30


def is_logged_in(client: Client) -> bool:
    return client.get(CUSTOMERS).status_code == 200


def test_a_new_key_ends_every_open_login(client, staff) -> None:
    client.force_login(staff)
    assert is_logged_in(client)

    # A leaked key is replaced: logins stamped with the old key stop working.
    with override_settings(SECRET_KEY=NEW_KEY):
        response = client.get(CUSTOMERS)

    assert response.status_code == 302
    assert response.url.startswith(LOGIN)


def test_the_old_key_as_a_fallback_keeps_people_logged_in(client, staff) -> None:
    client.force_login(staff)
    old_key = settings.SECRET_KEY

    # Planned rotation: keep the old key as a fallback, nobody is logged out.
    with override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[old_key]):
        assert is_logged_in(client)


def test_passwords_do_not_depend_on_the_key(staff) -> None:
    staff.set_password("correct-horse-battery")
    staff.save()

    with override_settings(SECRET_KEY=NEW_KEY):
        staff.refresh_from_db()
        assert staff.check_password("correct-horse-battery")


def test_the_key_never_appears_in_pages_or_the_log(
    client, admin, make_customer
) -> None:
    make_customer()
    client.force_login(admin)
    key = settings.SECRET_KEY

    for url in (
        CUSTOMERS,
        reverse("customer_table"),
        reverse("activity_log"),
        reverse("staff_list"),
        reverse("account"),
        reverse("register"),
    ):
        assert key not in client.get(url).text, url
    for entry in ActivityLog.objects.all():
        assert key not in str(entry.details)


def test_the_key_is_strong_enough_for_production() -> None:
    key = settings.SECRET_KEY

    # The same rule as Django's deploy check (security.W009).
    assert len(key) >= 50
    assert len(set(key)) >= 5
    assert not key.startswith("django-insecure-")
    assert key != "change-me"
