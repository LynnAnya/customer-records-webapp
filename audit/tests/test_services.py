import pytest

from audit.models import ActivityLog, AppendOnlyError
from audit.services import log_action

Action = ActivityLog.Action


def test_log_action_writes_exactly_one_row(admin) -> None:
    entry = log_action(
        Action.CUSTOMER_HIDE,
        user=admin,
        details={"customer_ids": [1, 2], "count": 2},
        ip_address="127.0.0.1",
    )

    assert ActivityLog.objects.count() == 1
    assert entry.user == admin
    assert entry.username == "admin1"
    assert entry.action == "customer_hide"
    assert entry.details == {"customer_ids": [1, 2], "count": 2}


@pytest.mark.django_db
def test_failed_login_is_logged_without_a_user() -> None:
    entry = log_action(Action.LOGIN_FAILED, username="someone")

    assert entry.user is None
    assert entry.username == "someone"


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["phone", "account_number", "anything_else"])
def test_details_reject_keys_that_are_not_allowed(key) -> None:
    with pytest.raises(ValueError):
        log_action(Action.COPY, details={key: "0800000000"})

    assert ActivityLog.objects.count() == 0


@pytest.mark.django_db
def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValueError):
        log_action("not_an_action")


def test_log_rows_cannot_be_updated(admin) -> None:
    entry = log_action(Action.LOGIN, user=admin)

    entry.action = Action.COPY
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        ActivityLog.objects.filter(pk=entry.pk).update(action=Action.COPY)

    entry.refresh_from_db()
    assert entry.action == "login"


def test_log_rows_cannot_be_deleted(admin) -> None:
    entry = log_action(Action.LOGIN, user=admin)

    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        ActivityLog.objects.all().delete()

    assert ActivityLog.objects.count() == 1
