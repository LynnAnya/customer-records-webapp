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
