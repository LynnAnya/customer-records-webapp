import pytest
from django.contrib.auth import get_user_model
from django.db import connection


def test_database_is_postgres() -> None:
    assert connection.vendor == "postgresql"


@pytest.mark.django_db
def test_new_user_is_staff_level_by_default() -> None:
    user = get_user_model().objects.create_user(username="nisa", password="x")

    assert user.is_admin is False
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.is_active is True
