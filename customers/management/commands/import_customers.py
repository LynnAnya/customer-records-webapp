from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from customers.importing import ImportFileError, import_customers

MAX_ERRORS_SHOWN = 50


class Command(BaseCommand):
    help = (
        "Import customers from an .xlsx file (first sheet, headers in row 1). "
        "Use --dry-run first: it checks every row and saves nothing."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", type=Path, help="Path to the .xlsx file.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Check the file, save nothing."
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        try:
            result = import_customers(options["path"], dry_run=dry_run)
        except ImportFileError as error:
            raise CommandError(str(error)) from error

        # Row numbers only below: never print phone or account numbers.
        self.stdout.write(f"Rows read: {result.rows_read}")
        if result.skipped_existing:
            self.stdout.write(
                f"Already in the database (skipped): {result.skipped_existing}"
            )
        if result.duplicate_phone_rows:
            self.stdout.write(
                self.style.WARNING(
                    "Phone already used by another customer (allowed, please check) "
                    f"in rows: {_rows(result.duplicate_phone_rows)}"
                )
            )
        if result.numeric_account_rows:
            self.stdout.write(
                self.style.WARNING(
                    "Account number is stored as a number in Excel, so a leading 0 "
                    "may be lost. Check these rows, or format the column as Text: "
                    f"{_rows(result.numeric_account_rows)}"
                )
            )

        if not result.ok:
            for line in result.errors[:MAX_ERRORS_SHOWN]:
                self.stdout.write(self.style.ERROR(line))
            hidden = len(result.errors) - MAX_ERRORS_SHOWN
            if hidden > 0:
                self.stdout.write(self.style.ERROR(f"... and {hidden} more problems"))
            raise CommandError(
                f"{len(result.errors)} problems found. Nothing was saved. "
                "Fix the file and run again."
            )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run OK: {result.created} customers would be imported. "
                    "Nothing was saved."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Imported {result.created} customers.")
            )


def _rows(numbers: list[int]) -> str:
    shown = ", ".join(str(number) for number in numbers[:30])
    return f"{shown} ..." if len(numbers) > 30 else shown
