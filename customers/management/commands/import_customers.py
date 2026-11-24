from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from customers.importing import ImportFileError, import_customers

MAX_ERRORS_SHOWN = 50


class Command(BaseCommand):
    help = (
        "Import customers from an .xlsx file (the first sheet with the right "
        "headers in row 1, or --sheet). "
        "Use --dry-run first: it checks every row and saves nothing."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", type=Path, help="Path to the .xlsx file.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Check the file, save nothing."
        )
        parser.add_argument("--sheet", help="Sheet (tab) name to read.")

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        try:
            result = import_customers(
                options["path"], dry_run=dry_run, sheet=options["sheet"]
            )
        except ImportFileError as error:
            raise CommandError(str(error)) from error

        # Row numbers only below: never print phone or account numbers.
        if len(result.sheet_names) > 1:
            self.stdout.write(f"Sheet: {result.sheet_name}")
        self.stdout.write(f"Rows read: {result.rows_read}")
        if result.skipped_duplicates:
            self.stdout.write(
                "Exact repeats of a saved customer or an earlier row "
                f"(skipped): {result.skipped_duplicates}"
            )
        if result.duplicate_phone_rows:
            self.stdout.write(
                self.style.WARNING(
                    "Phone already used by another customer (allowed, please check) "
                    f"in rows: {_rows(result.duplicate_phone_rows)}"
                )
            )
        if result.invalid_account_rows:
            self.stdout.write(
                self.style.WARNING(
                    "Account number is not a number, saved as '-' (please check) "
                    f"in rows: {_rows(result.invalid_account_rows)}"
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
