"""SITE_NAME: the name shown in the app comes from the environment, not the code."""

from django.template.loader import render_to_string
from django.urls import reverse

from config.tests.test_settings_render import settings_value

NAME = "Example Trading Co."


def test_without_site_name_the_generic_name_is_used() -> None:
    assert settings_value({"SITE_NAME": ""}, "s.SITE_NAME") == "Customer Records"


def test_site_name_is_read_from_the_environment() -> None:
    assert settings_value({"SITE_NAME": NAME}, "s.SITE_NAME") == NAME


def test_login_page_shows_the_configured_name(client, settings) -> None:
    settings.SITE_NAME = NAME

    page = client.get(reverse("login")).text

    assert f"<title>เข้าสู่ระบบ · {NAME}</title>" in page
    assert page.count(NAME) >= 3  # title, brand, big heading


def test_qr_form_shows_the_configured_name(client, settings) -> None:
    settings.SITE_NAME = NAME

    page = client.get(reverse("register")).text

    assert f" · {NAME}</title>" in page
    assert page.count(NAME) >= 2  # title and brand


def test_logged_in_pages_show_the_configured_name(client, settings, staff) -> None:
    settings.SITE_NAME = NAME
    client.force_login(staff)

    page = client.get(reverse("customer_list")).text

    assert f" · {NAME}</title>" in page
    assert page.count(NAME) >= 3  # title, sidebar, phone top bar


def test_name_is_escaped(client, settings) -> None:
    settings.SITE_NAME = "<b>A & B</b>"

    page = client.get(reverse("login")).text

    assert "<b>A & B</b>" not in page
    assert "&lt;b&gt;A &amp; B&lt;/b&gt;" in page


def test_error_page_works_without_the_name() -> None:
    page = render_to_string("500.html")  # no template data, like Django's handler

    assert "ระบบขัดข้องชั่วคราว" in page
    assert "<title>ระบบขัดข้อง</title>" in page
