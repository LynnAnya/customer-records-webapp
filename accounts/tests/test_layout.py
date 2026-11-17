"""The app frame: menu by role, self-hosted assets. All data is fake."""

import re

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from accounts import navigation
from accounts.navigation import NavItem, nav_items

CUSTOMERS = reverse("customer_list")


@pytest.fixture
def menu_with_admin_item(monkeypatch):
    items = (
        NavItem(label="ลูกค้า", url_name="customer_list", icon="users"),
        NavItem(
            label="เฉพาะแอดมิน", url_name="customer_list", icon="lock", admin_only=True
        ),
    )
    monkeypatch.setattr(navigation, "NAV_ITEMS", items)


def test_staff_never_get_admin_only_menu_items(staff, menu_with_admin_item) -> None:
    assert [item.label for item in nav_items(staff)] == ["ลูกค้า"]


def test_admin_gets_every_menu_item(admin, menu_with_admin_item) -> None:
    assert [item.label for item in nav_items(admin)] == ["ลูกค้า", "เฉพาะแอดมิน"]


def test_anonymous_user_gets_no_menu() -> None:
    assert nav_items(AnonymousUser()) == []


def test_admin_only_item_is_not_in_the_staff_page(
    client, staff, menu_with_admin_item
) -> None:
    client.force_login(staff)

    assert "เฉพาะแอดมิน" not in client.get(CUSTOMERS).text


def test_admin_only_item_is_in_the_admin_page(
    client, admin, menu_with_admin_item
) -> None:
    client.force_login(admin)

    assert "เฉพาะแอดมิน" in client.get(CUSTOMERS).text


def test_menu_has_the_same_items_for_both_roles_and_a_post_logout(
    client, admin, staff
) -> None:
    for user in (admin, staff):
        client.force_login(user)
        page = client.get(CUSTOMERS).text

        assert "ลูกค้า" in page
        assert "บัญชีผู้ใช้" in page
        assert "ตั้งค่า" in page
        assert f'<form method="post" action="{reverse("logout")}"' in page


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["login", "register", "register_thanks"])
def test_public_pages_load_no_third_party_assets(client, name) -> None:
    page = client.get(reverse(name)).text

    assert "https://" not in page
    assert "http://" not in page.replace("http://www.w3.org", "")
    assert "/static/css/app.css" in page


def test_app_pages_load_no_third_party_assets(client, staff) -> None:
    client.force_login(staff)
    page = client.get(CUSTOMERS).text

    assert "https://" not in page
    assert "/static/js/alpine-" in page


@pytest.mark.django_db
def test_css_and_js_addresses_carry_a_version(client) -> None:
    # Otherwise browsers keep showing an old stylesheet after an update.
    page = client.get(reverse("login")).text

    assert re.search(r'href="/static/css/app\.css\?v=\d+"', page)
    assert re.search(r'src="/static/js/app\.js\?v=\d+"', page)
