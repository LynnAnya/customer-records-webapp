"""Log detail page, CSV download and the yearly archive. All data is fake."""

import csv
import gzip
import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from audit.export import safe_cell
from audit.models import ActivityLog
from audit.services import log_action
from audit.tests.test_views import backdate, raw_sql

Action = ActivityLog.Action
EXPORT = reverse("activity_log_export")


@pytest.fixture
def as_admin(client, admin):
    client.force_login(admin)
    raw_sql("DELETE FROM audit_activitylog")
    return client


def names_entry(user, count: int) -> ActivityLog:
    names = [f"ลูกค้า{index:02d}" for index in range(count)]
    return log_action(
        Action.COPY,
        user=user,
        details={"customer_ids": list(range(count)), "customer_names": names,
                 "count": count},
    )  # fmt: skip


def read_csv(response) -> list[list[str]]:
    text = b"".join(response.streaming_content).decode("utf-8")
    assert text.startswith("﻿")  # Excel opens Thai text correctly
    return list(csv.reader(io.StringIO(text[1:])))


# --- Detail page ----------------------------------------------------------


def test_detail_page_lists_every_customer_name(as_admin, admin) -> None:
    entry = names_entry(admin, 51)

    response = as_admin.get(reverse("activity_log_detail", args=[entry.pk]))

    assert response.status_code == 200
    for index in range(51):
        assert f"ลูกค้า{index:02d}" in response.text
    assert "51 ราย" in response.text


def test_list_links_each_row_to_its_detail_page(as_admin, admin) -> None:
    entry = names_entry(admin, 2)

    response = as_admin.get(reverse("activity_log"))

    assert reverse("activity_log_detail", args=[entry.pk]) in response.text


def test_detail_back_link_only_goes_to_the_log(as_admin, admin) -> None:
    entry = names_entry(admin, 1)
    url = reverse("activity_log_detail", args=[entry.pk])

    good = as_admin.get(url, {"back": "/activity/?action=copy"})
    evil = as_admin.get(url, {"back": "https://evil.example/"})

    assert good.context["back_url"] == "/activity/?action=copy"
    assert evil.context["back_url"] == reverse("activity_log")


def test_detail_is_admin_only_and_writes_nothing(client, staff, admin) -> None:
    entry = names_entry(admin, 1)
    before = ActivityLog.objects.count()
    client.force_login(staff)

    response = client.get(reverse("activity_log_detail", args=[entry.pk]))

    assert response.status_code == 403
    assert ActivityLog.objects.count() == before + 1  # only the staff login


def test_last_updated_label_shows_the_date(as_admin) -> None:
    response = as_admin.get(reverse("activity_log"))

    assert response.context["updated_at"].strftime("%Y") in response.text


# --- CSV download ---------------------------------------------------------


def test_csv_download_of_filtered_rows(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin, details={"count": 1})
    log_action(Action.PDF_EXPORT, user=admin, details={"count": 1})

    response = as_admin.post(EXPORT, {"scope": "filtered", "action": "copy"})

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Cache-Control"] == "no-store"
    rows = read_csv(response)
    assert rows[0][0] == "รหัส"
    assert [row[4] for row in rows[1:]] == ["copy"]


def test_csv_download_of_everything_ignores_filters(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin)
    log_action(Action.PDF_EXPORT, user=admin)

    rows = read_csv(as_admin.post(EXPORT, {"scope": "all", "action": "copy"}))

    assert sorted(row[4] for row in rows[1:]) == ["copy", "pdf_export"]


def test_csv_download_is_logged_once_with_the_count(as_admin, admin) -> None:
    log_action(Action.COPY, user=admin)

    as_admin.post(EXPORT, {"scope": "all"})

    entry = ActivityLog.objects.get(action=Action.LOG_EXPORTED)
    assert entry.user == admin
    assert entry.details == {"count": 1}


def test_csv_lists_every_name_and_blocks_formulas(as_admin, admin) -> None:
    names_entry(admin, 8)
    log_action(
        Action.CUSTOMER_CREATE,
        user=admin,
        details={"customer_ids": [1], "customer_names": ["=HYPERLINK(1)"], "count": 1},
    )

    rows = read_csv(as_admin.post(EXPORT, {"scope": "all"}))

    text = "\n".join(",".join(row) for row in rows)
    assert "ลูกค้า07" in text
    assert "'=HYPERLINK(1)" in text


def test_csv_download_is_admin_only_and_post_only(client, staff, admin) -> None:
    client.force_login(staff)
    assert client.post(EXPORT, {"scope": "all"}).status_code == 403

    client.force_login(admin)
    assert client.get(EXPORT).status_code == 405


@pytest.mark.parametrize(
    ("value", "expected"),
    [("=1+1", "'=1+1"), ("+66", "'+66"), ("@x", "'@x"), ("-", "-"), ("สมชาย", "สมชาย")],
)
def test_safe_cell(value, expected) -> None:
    assert safe_cell(value) == expected


# --- Yearly archive -------------------------------------------------------


@pytest.fixture
def old_and_new(admin, db):
    raw_sql("DELETE FROM audit_activitylog")
    old = [log_action(Action.COPY, user=admin) for _ in range(3)]
    for entry in old:
        backdate(entry, timedelta(days=400))
    new = log_action(Action.PDF_EXPORT, user=admin)
    return old, new


def test_archive_dry_run_changes_nothing(old_and_new, tmp_path, capsys) -> None:
    call_command("archive_activity_log", "--dry-run")

    assert ActivityLog.objects.count() == 4
    assert "3 rows" in capsys.readouterr().out


def test_archive_writes_the_file_then_deletes_old_rows(
    old_and_new, tmp_path, settings
) -> None:
    settings.BASE_DIR = tmp_path / "project"
    old, new = old_and_new
    output = tmp_path / "log-2025.csv.gz"

    call_command("archive_activity_log", "--output", str(output))

    with gzip.open(output, "rt", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    assert [int(row[0]) for row in rows[1:]] == [entry.pk for entry in old]
    remaining = list(ActivityLog.objects.order_by("id"))
    assert remaining[0] == new
    assert remaining[1].action == "log_archived"
    assert remaining[1].details == {"count": 3}
    assert len(remaining) == 2


@pytest.mark.parametrize(
    "problem", ["inside_project", "exists", "wrong_name", "too_young"]
)
def test_archive_refuses_unsafe_runs_and_deletes_nothing(
    old_and_new, tmp_path, settings, problem
) -> None:
    settings.BASE_DIR = tmp_path
    output = tmp_path.parent / f"{tmp_path.name}-archive.csv.gz"
    args = ["--output", str(output)]
    if problem == "inside_project":
        args = ["--output", str(tmp_path / "log.csv.gz")]
    elif problem == "exists":
        output.write_text("keep me")
    elif problem == "wrong_name":
        args = ["--output", str(tmp_path.parent / "log.txt")]
    elif problem == "too_young":
        args += ["--older-than-days", "30"]

    with pytest.raises(CommandError):
        call_command("archive_activity_log", *args)

    assert ActivityLog.objects.count() == 4
    if problem == "exists":
        assert output.read_text() == "keep me"
