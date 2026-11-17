from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from audit.archive import MIN_DAYS, ArchiveError, archive_old_logs


class Command(BaseCommand):
    help = (
        "Move activity log rows older than N days (default 365) into a "
        "compressed CSV file outside the project, then delete them from the "
        "database. Use --dry-run first."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--older-than-days", type=int, default=MIN_DAYS)
        parser.add_argument(
            "--output", type=Path, help="New .csv.gz file outside the project."
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Count only, change nothing."
        )

    def handle(self, *args, **options) -> None:
        try:
            result = archive_old_logs(
                older_than_days=options["older_than_days"],
                output=options["output"],
                dry_run=options["dry_run"],
            )
        except ArchiveError as error:
            raise CommandError(str(error)) from error

        cutoff = timezone.localtime(result.cutoff).strftime("%Y-%m-%d %H:%M")
        if options["dry_run"]:
            self.stdout.write(
                f"Dry run: {result.count} rows are older than {cutoff}. "
                "Nothing was written or deleted."
            )
        elif result.count == 0:
            self.stdout.write(f"No rows older than {cutoff}. Nothing to do.")
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Archived {result.deleted} rows older than {cutoff} to "
                    f"{result.output} and removed them from the database. "
                    "Keep the file in private storage with the backups."
                )
            )
