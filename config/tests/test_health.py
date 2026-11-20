"""Render's health check."""

import pytest
from django.db import DatabaseError
from django.urls import reverse

URL = reverse("healthz")


@pytest.mark.django_db
def test_answers_ok_without_logging_in(client) -> None:
    response = client.get(URL)

    assert response.status_code == 200
    assert response.content == b"ok"
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_says_unhealthy_when_the_database_is_down(client, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise DatabaseError("connection refused")

    monkeypatch.setattr("django.db.backends.utils.CursorWrapper.execute", broken)

    response = client.get(URL)

    assert response.status_code == 503
    assert b"connection refused" not in response.content  # no error details out


@pytest.mark.django_db
def test_only_answers_get(client) -> None:
    assert client.post(URL).status_code == 405


@pytest.mark.django_db
def test_missing_pages_show_the_thai_page(client, settings) -> None:
    settings.DEBUG = False

    response = client.get("/no-such-page/")

    assert response.status_code == 404
    assert "ไม่พบหน้านี้" in response.text


def test_the_error_page_needs_no_request_or_database() -> None:
    from django.template.loader import render_to_string

    page = render_to_string("500.html")  # exactly how Django renders it

    assert "ระบบขัดข้องชั่วคราว" in page


@pytest.mark.django_db
def test_favicon_ico_points_to_the_icon(client) -> None:
    response = client.get("/favicon.ico")

    assert response.status_code == 302
    assert response.url.endswith("img/favicon.svg")


def test_unknown_host_logs_one_line_without_traceback() -> None:
    import logging
    import sys

    from config.log_filters import OneLine

    record = logging.LogRecord(
        "x", logging.ERROR, "", 0, "Invalid HTTP_HOST", None, None
    )
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = sys.exc_info()

    OneLine().filter(record)

    assert record.exc_info is None
    assert logging.Formatter().format(record) == "Invalid HTTP_HOST"
