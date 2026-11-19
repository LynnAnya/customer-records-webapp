"""Activity Log page (admin only, read-only). All data is fake."""

from datetime import timedelta

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from accounts.navigation import nav_items
from audit.labels import ACTION_LABELS, describe_details, time_ago
from audit.models import ActivityLog
from audit.services import log_action

Action = ActivityLog.Action
PAGE = reverse("activity_log")
TABLE = reverse("activity_log_table")
URLS = [PAGE, TABLE]


def entries(response) -> list[ActivityLog]:
    return list(response.context["page"].object_list)


def raw_sql(sql: str, params: list | None = None) -> None:
    """The log refuses updates and deletes through Django, so tests that need
    an old or empty log go around it with plain SQL."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])


def backdate(entry: ActivityLog, age: timedelta) -> None:
    raw_sql(
        "UPDATE audit_activitylog SET created_at = %s WHERE id = %s",
        [timezone.now() - age, entry.pk],
    )


@pytest.fixture
def as_admin(client, admin):
    client.force_login(admin)
    # Logging in writes its own row; start each test from an empty log.
    raw_sql("DELETE FROM audit_activitylog")
    return client


# --- Access ---------------------------------------------------------------


@pytest.mark.parametrize("url", URLS)
def test_staff_get_403(client, staff, url) -> None:
    client.force_login(staff)

    assert client.get(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", URLS)
def test_anonymous_users_are_sent_to_login(client, url) -> None:
    response = client.get(url)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_menu_item_is_for_admins_only(client, admin, staff) -> None:
    assert "activity_log" in [item.url_name for item in nav_items(admin)]
    assert "activity_log" not in [item.url_name for item in nav_items(staff)]

    client.force_login(staff)
    assert PAGE not in client.get(reverse("customer_list")).text
    client.force_login(admin)
    assert PAGE in client.get(reverse("customer_list")).text


# --- Read-only ------------------------------------------------------------


@pytest.mark.parametrize("url", URLS)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_page_accepts_no_changes(as_admin, admin, url, method) -> None:
    log_action(Action.COPY, user=admin)

    response = getattr(as_admin, method)(url)

    assert response.status_code == 405
    assert ActivityLog.objects.count() == 1


# --- Content --------------------------------------------------------------


def test_rows_are_newest_first_with_thai_labels(as_admin, admin) -> None:
    log_action(Action.CUSTOMER_CREATE, user=admin, details={"customer_names": ["เก่า"]})
    log_action(Action.CUSTOMER_HIDE, user=admin, details={"customer_names": ["ใหม่"]})

    response = as_admin.get(PAGE)

    assert [entry.action for entry in entries(response)] == [
        "customer_hide",
        "customer_create",
    ]
    assert "ซ่อนลูกค้า" in response.text
    assert "เพิ่มลูกค้า" in response.text
    assert "customer_hide" not in response.text.split("<table")[1]


def test_every_action_code_has_a_thai_label() -> None:
    assert set(ACTION_LABELS) == set(Action.values)


def test_details_are_written_in_plain_words() -> None:
    assert (
        describe_details({"customer_names": ["สมชาย ใจดี"], "count": 1}) == "สมชาย ใจดี"
    )
    assert (
        describe_details({"customer_names": ["ก", "ข"], "count": 2}) == "ก, ข (2 ราย)"
    )
    many = {"customer_names": [str(n) for n in range(8)], "count": 8}
    assert describe_details(many) == "0, 1, 2, 3, 4 และอีก 3 ราย (8 ราย)"
    assert describe_details({"count": 30}) == "(30 ราย)"
    assert describe_details({"target_username": "nisa"}) == "บัญชี nisa"
    assert describe_details({}) == ""


def test_failed_login_shows_the_typed_username_safely(as_admin) -> None:
    log_action(Action.LOGIN_FAILED, username="<script>alert(1)</script>")

    page = as_admin.get(PAGE).text

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "เข้าสู่ระบบไม่สำเร็จ" in page


def test_relative_time_with_exact_time_on_hover(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin)
    backdate(log_action(Action.SHARE, user=admin), timedelta(hours=3))

    page = as_admin.get(PAGE).text

    assert "เมื่อสักครู่" in page
    assert "3 ชั่วโมงที่แล้ว" in page
    assert 'title="' in page


def test_relative_time_steps() -> None:
    now = timezone.now()

    def ago(**delta) -> str:
        return time_ago(now - timedelta(**delta), now)

    assert ago(seconds=20) == "เมื่อสักครู่"
    assert ago(minutes=2) == "2 นาทีที่แล้ว"
    assert ago(hours=5) == "5 ชั่วโมงที่แล้ว"
    assert ago(days=3) == "3 วันที่แล้ว"
    assert "ที่แล้ว" not in ago(days=45)


# --- Filters --------------------------------------------------------------


def test_filter_by_user(as_admin, admin, staff) -> None:
    log_action(Action.COPY, user=admin)
    log_action(Action.COPY, user=staff)

    response = as_admin.get(TABLE, {"user": staff.pk})

    assert [entry.username for entry in entries(response)] == ["staff1"]


def test_filter_by_action(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin)
    log_action(Action.PDF_EXPORT, user=admin)

    response = as_admin.get(TABLE, {"action": "pdf_export"})

    assert [entry.action for entry in entries(response)] == ["pdf_export"]


def test_filter_by_date_range(as_admin, admin) -> None:
    backdate(log_action(Action.COPY, user=admin), timedelta(days=10))
    log_action(Action.SHARE, user=admin)
    today = timezone.localdate()

    recent = as_admin.get(TABLE, {"from": str(today - timedelta(days=1))})
    older = as_admin.get(TABLE, {"to": str(today - timedelta(days=5))})

    assert [entry.action for entry in entries(recent)] == ["share"]
    assert [entry.action for entry in entries(older)] == ["copy"]


@pytest.mark.parametrize(
    "bad",
    [
        {"user": "abc"},
        {"user": "-1"},
        {"action": "drop_table"},
        {"from": "x"},
        {"to": "2026-99-99"},
    ],
)
def test_invalid_filters_are_ignored(as_admin, admin, bad) -> None:
    log_action(Action.COPY, user=admin)

    response = as_admin.get(TABLE, bad)

    assert response.status_code == 200
    assert response.context["filters"].active_count == 0
    assert len(entries(response)) == 1


# --- Pagination and refresh -----------------------------------------------


def test_pagination_shows_50_per_page(as_admin, admin) -> None:
    for _ in range(53):
        log_action(Action.COPY, user=admin)

    first = as_admin.get(TABLE)
    second = as_admin.get(TABLE, {"page": 2})

    assert len(entries(first)) == 50
    assert len(entries(second)) == 3
    assert "หน้า 1 / 2" in first.text


def test_fragment_refreshes_itself_and_keeps_filters(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin)

    response = as_admin.get(TABLE, {"action": "copy"})

    assert "<html" not in response.text
    assert 'hx-trigger="every 10s' in response.text
    assert "action=copy" in response.text.split('hx-get="')[1].split('"')[0]
    assert "อัปเดตล่าสุด" in response.text
    assert response["HX-Push-Url"] == f"{PAGE}?action=copy"


def test_viewing_the_log_does_not_write_to_the_log(as_admin) -> None:
    as_admin.get(PAGE)
    as_admin.get(TABLE)

    assert ActivityLog.objects.count() == 0


# --- Phone cards ----------------------------------------------------------


def test_phone_card_is_one_link_to_the_detail_page(as_admin, admin) -> None:
    entry = log_action(Action.COPY, user=admin, details={"count": 1})

    page = as_admin.get(TABLE).text

    detail = reverse("activity_log_detail", args=[entry.pk])
    assert f'<a class="link-card" href="{detail}?back=' in page
    assert '<span class="sr-only">ดูรายละเอียด</span>' in page
