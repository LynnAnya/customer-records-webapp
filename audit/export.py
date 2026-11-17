"""Activity log rows as CSV, for the admin download and the yearly archive.

The log never holds phone or account numbers (see `log_action`), so a CSV of
it does not either. Cells that start like a spreadsheet formula get a leading
apostrophe, because customer names come from the public form.
"""

import csv
from collections.abc import Iterator

from django.db.models import QuerySet
from django.utils import timezone

from audit.labels import action_label, describe_details
from audit.models import ActivityLog

HEADER = [
    "รหัส",
    "วันที่เวลา",
    "ชื่อผู้ใช้",
    "การกระทำ",
    "รหัสการกระทำ",
    "รายละเอียด",
    "จำนวน",
    "IP",
]
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """Stop Excel from running a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    if text != "-" and text.startswith(FORMULA_STARTS):
        return f"'{text}"
    return text


def log_row(entry: ActivityLog) -> list[str]:
    details = entry.details or {}
    return [
        str(entry.pk),
        timezone.localtime(entry.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        safe_cell(entry.username),
        action_label(entry.action),
        entry.action,
        safe_cell(describe_details(details, max_names=None)),
        str(details.get("count", "")),
        entry.ip_address or "",
    ]


def csv_lines(logs: QuerySet[ActivityLog]) -> Iterator[list[str]]:
    """Header, then one row per log entry. Reads the database in chunks."""
    yield HEADER
    for entry in logs.iterator(chunk_size=2000):
        yield log_row(entry)


class _Echo:
    """A file-like object that hands back what is written (for streaming)."""

    def write(self, value: str) -> str:
        return value


def stream_csv(logs: QuerySet[ActivityLog]) -> Iterator[str]:
    """CSV text in pieces, with a BOM so Excel reads the Thai text as UTF-8."""
    writer = csv.writer(_Echo())
    yield "﻿"
    for line in csv_lines(logs):
        yield writer.writerow(line)
