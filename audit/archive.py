"""Yearly clean-up of old activity log rows. Used by `archive_activity_log`.

This is the one exception to "the log is append-only" (decided 2026-11-17):
rows older than the cut-off are first written to a compressed CSV file and the
file is read back and checked. Only then are those rows deleted, in one
transaction, and one `log_archived` row records how many. It never runs from
a web page.
"""

import csv
import gzip
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from audit.export import HEADER, csv_lines
from audit.models import ActivityLog
from audit.services import log_action

MIN_DAYS = 365  # decided: 12 months stay in the app


class ArchiveError(Exception):
    """The archive cannot run safely. Nothing was deleted."""


@dataclass
class ArchiveResult:
    cutoff: datetime
    count: int
    deleted: int = 0
    output: Path | None = None


def _check_output(output: Path) -> Path:
    output = output.expanduser().resolve()
    if output.exists():
        raise ArchiveError(f"{output} already exists. Choose a new file name.")
    if not output.parent.is_dir():
        raise ArchiveError(f"Folder not found: {output.parent}")
    if output.is_relative_to(Path(settings.BASE_DIR).resolve()):
        raise ArchiveError(
            "The archive must be saved outside the project folder (never in git)."
        )
    if not output.name.endswith(".csv.gz"):
        raise ArchiveError("The file name must end with .csv.gz")
    return output


def _count_rows(path: Path) -> tuple[int, int]:
    """Read the file back: (data rows, highest log id)."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        if next(reader, None) != HEADER:
            raise ArchiveError("The archive file header is wrong. Nothing deleted.")
        ids = [int(row[0]) for row in reader]
    return len(ids), max(ids, default=0)


def archive_old_logs(
    *, older_than_days: int, output: Path | None, dry_run: bool
) -> ArchiveResult:
    if older_than_days < MIN_DAYS:
        raise ArchiveError(f"Keep at least {MIN_DAYS} days of log in the app.")
    cutoff = timezone.now() - timedelta(days=older_than_days)
    old = ActivityLog.objects.filter(created_at__lt=cutoff).order_by("id")
    result = ArchiveResult(cutoff=cutoff, count=old.count())
    if dry_run or result.count == 0:
        return result
    if output is None:
        raise ArchiveError("--output is required.")
    result.output = path = _check_output(output)

    with transaction.atomic():
        # Lock the old rows so the file and the delete see exactly the same set.
        ids = list(old.select_for_update().values_list("id", flat=True))
        with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            for line in csv_lines(old.filter(id__in=ids)):
                writer.writerow(line)

        written, highest = _count_rows(path)
        if written != len(ids) or highest != max(ids):
            raise ArchiveError("The archive file does not match. Nothing deleted.")

        # The model refuses deletes on purpose; this is the single exception.
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {ActivityLog._meta.db_table} "  # noqa: S608
                "WHERE id = ANY(%s) AND created_at < %s",
                [ids, cutoff],
            )
            result.deleted = cursor.rowcount
        if result.deleted != len(ids):
            raise ArchiveError("Delete count does not match. Nothing deleted.")

        log_action(
            ActivityLog.Action.LOG_ARCHIVED,
            username="archive_activity_log",
            details={"count": result.deleted},
        )
    return result
