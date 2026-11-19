"""The theme is saved on the account, so it follows the person, not the browser."""

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User
from audit.models import ActivityLog

THEME = reverse("set_theme")
CUSTOMERS = reverse("customer_list")


def html_tag(page: str) -> str:
    return page[page.index("<html") : page.index(">", page.index("<html")) + 1]


def test_new_accounts_follow_the_device(admin, staff) -> None:
    assert admin.theme == staff.theme == User.Theme.SYSTEM


def test_choosing_a_theme_saves_it_on_the_account(client, staff) -> None:
    client.force_login(staff)

    response = client.post(THEME, {"theme": "dark"})

    assert response.status_code == 204
    staff.refresh_from_db()
    assert staff.theme == "dark"


def test_each_person_keeps_their_own_theme_in_the_same_browser(
    client, admin, staff
) -> None:
    client.force_login(admin)
    client.post(THEME, {"theme": "dark"})
    client.logout()

    client.force_login(staff)
    page = client.get(CUSTOMERS).text

    assert 'data-theme="system"' in html_tag(page)
    assert 'class="dark"' not in html_tag(page)


def test_the_theme_follows_the_person_to_another_device(admin) -> None:
    laptop, phone = Client(), Client()
    laptop.force_login(admin)
    laptop.post(THEME, {"theme": "dark"})

    phone.force_login(admin)
    tag = html_tag(phone.get(CUSTOMERS).text)

    assert 'data-theme="dark"' in tag
    assert 'class="dark"' in tag  # dark before any JavaScript runs


@pytest.mark.parametrize("bad", ["", "blue", "DARK", "<script>"])
def test_unknown_values_are_refused(client, staff, bad) -> None:
    client.force_login(staff)

    response = client.post(THEME, {"theme": bad})

    assert response.status_code == 400
    staff.refresh_from_db()
    assert staff.theme == "system"


@pytest.mark.django_db
def test_anonymous_users_cannot_save_a_theme(client) -> None:
    response = client.post(THEME, {"theme": "dark"})

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_saving_needs_post_and_a_csrf_token(staff) -> None:
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(staff)

    assert strict.get(THEME).status_code == 405
    assert strict.post(THEME, {"theme": "dark"}).status_code == 403
    staff.refresh_from_db()
    assert staff.theme == "system"


def test_saving_a_theme_writes_no_log_row(client, staff) -> None:
    client.force_login(staff)
    before = ActivityLog.objects.count()

    client.post(THEME, {"theme": "light"})

    assert ActivityLog.objects.count() == before
