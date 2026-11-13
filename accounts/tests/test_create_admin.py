import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db

COMMAND = "accounts.management.commands.create_admin"
GOOD_PASSWORD = "correct-horse-battery"


@pytest.fixture
def prompts(monkeypatch):
    """Answer the command's prompts without a real terminal."""

    def _answer(password: str, again: str | None = None) -> None:
        names = iter(["สมชาย", "ใจดี"])
        passwords = iter([password, password if again is None else again])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(names))
        monkeypatch.setattr(f"{COMMAND}.getpass.getpass", lambda _p: next(passwords))

    return _answer


def test_create_admin_sets_only_the_is_admin_flag(prompts) -> None:
    prompts(GOOD_PASSWORD)

    call_command("create_admin", "boss")

    user = get_user_model().objects.get(username="boss")
    assert user.is_admin is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.first_name == "สมชาย"
    assert user.check_password(GOOD_PASSWORD)
    assert user.password != GOOD_PASSWORD  # stored hashed


@pytest.mark.parametrize(
    ("password", "again"),
    [
        (GOOD_PASSWORD, "something-else"),  # the two entries differ
        ("short1", None),  # under 8 characters
        ("12345678", None),  # all numbers
        ("password", None),  # too common
    ],
)
def test_create_admin_rejects_bad_passwords(prompts, password, again) -> None:
    prompts(password, again)

    with pytest.raises(CommandError):
        call_command("create_admin", "boss")

    assert not get_user_model().objects.filter(username="boss").exists()


def test_create_admin_refuses_an_existing_username(prompts, staff) -> None:
    prompts(GOOD_PASSWORD)

    with pytest.raises(CommandError):
        call_command("create_admin", "staff1")

    staff.refresh_from_db()
    assert staff.is_admin is False
