"""Read customers from an Excel file and save them. Used by `import_customers`.

Every row goes through `ImportCustomerForm`: the same rules as the app forms,
except that empty cells are allowed and saved as "-". Nothing here prints or
returns a phone or account number: problems are reported by row and column.
"""

from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from audit.models import ActivityLog
from audit.services import log_action
from customers.forms import ImportCustomerForm
from customers.models import MISSING, Customer

# Header text (lower-case, spaces removed) -> form field.
HEADER_ALIASES: dict[str, str] = {
    "ชื่อ": "name",
    "ชื่อ-นามสกุล": "name",
    "ชื่อนามสกุล": "name",
    "ชื่อ-สกุล": "name",
    "name": "name",
    "fullname": "name",
    "ทะเบียนรถ": "license_plate",
    "ทะเบียน": "license_plate",
    "เลขทะเบียน": "license_plate",
    "licenseplate": "license_plate",
    "license_plate": "license_plate",
    "เบอร์โทรศัพท์": "phone",
    "เบอร์โทร": "phone",
    "โทรศัพท์": "phone",
    "เบอร์": "phone",
    "phone": "phone",
    "ธนาคาร": "bank_name",
    "bank": "bank_name",
    "bank_name": "bank_name",
    "หมายเลขบัญชี": "account_number",
    "เลขที่บัญชี": "account_number",
    "เลขบัญชี": "account_number",
    "บัญชี": "account_number",
    "accountnumber": "account_number",
    "account_number": "account_number",
    "ผู้แนะนำ": "referral",
    "referral": "referral",
}
# Columns that must exist. Their cells may be empty (saved as "-").
REQUIRED_FIELDS = ("name", "license_plate", "phone", "bank_name", "account_number")
FIELD_LABELS = {
    "name": "ชื่อ",
    "license_plate": "ทะเบียนรถ",
    "phone": "เบอร์โทร",
    "bank_name": "ธนาคาร",
    "account_number": "หมายเลขบัญชี",
    "referral": "ผู้แนะนำ",
}


class ImportFileError(Exception):
    """The file cannot be used at all (missing, wrong type, wrong headers)."""


@dataclass
class ImportResult:
    rows_read: int = 0
    created: int = 0
    skipped_existing: int = 0
    duplicate_phone_rows: list[int] = field(default_factory=list)
    numeric_account_rows: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = True

    @property
    def ok(self) -> bool:
        return not self.errors


def _header_key(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _cell_text(value: object) -> str:
    """Excel cell -> text. Numbers lose any '.0' (Excel stores 812345678.0)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _phone_text(value: object) -> str:
    """Excel drops the leading 0 of a phone stored as a number. A 9-digit number
    gets it back. Text cells are kept as written."""
    text = _cell_text(value)
    if isinstance(value, int | float) and len(text) == 9 and text.isdigit():
        return f"0{text}"
    return text


def _read_rows(path: Path) -> tuple[list[str], list[tuple[int, dict[str, object]]]]:
    """Return the mapped columns and (Excel row number, raw values) pairs."""
    if not path.is_file():
        raise ImportFileError(f"File not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ImportFileError("The file must be an .xlsx Excel file.")
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises several unrelated types
        raise ImportFileError("The file could not be opened as Excel.") from error

    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        header_row = next(rows, None)
        if header_row is None:
            raise ImportFileError("The first sheet is empty.")

        columns = [HEADER_ALIASES.get(_header_key(cell), "") for cell in header_row]
        found = {name for name in columns if name}
        missing = [FIELD_LABELS[name] for name in REQUIRED_FIELDS if name not in found]
        if missing:
            seen = ", ".join(str(cell) for cell in header_row if cell) or "(none)"
            raise ImportFileError(
                f"Missing columns: {', '.join(missing)}. Headers found: {seen}"
            )

        data: list[tuple[int, dict[str, object]]] = []
        for row_number, row in enumerate(rows, start=2):
            # Rows can be shorter than the header row; missing cells are blank.
            cells = zip(columns, row, strict=False)
            values = {name: cell for name, cell in cells if name}
            if any(_cell_text(cell) for cell in values.values()):
                data.append((row_number, values))
        return sorted(found), data
    finally:
        workbook.close()


def _form_data(values: dict[str, object]) -> dict[str, str]:
    data = {name: _cell_text(cell) for name, cell in values.items()}
    data["phone"] = _phone_text(values.get("phone"))
    data.setdefault("referral", "")
    return data


def import_customers(path: Path, *, dry_run: bool) -> ImportResult:
    """Validate every row, then save all of them or none.

    `dry_run=True` checks everything and writes nothing. A real run is one
    transaction: any invalid row stops the import with nothing saved.
    """
    _columns, rows = _read_rows(path)
    result = ImportResult(rows_read=len(rows), dry_run=dry_run)

    existing_phones = set(Customer.objects.values_list("phone", flat=True))
    existing_people = set(
        Customer.objects.values_list("name", "phone", "account_number")
    )
    phones_in_file: set[str] = set()
    forms: list[ImportCustomerForm] = []

    for row_number, values in rows:
        if isinstance(values.get("account_number"), int | float):
            result.numeric_account_rows.append(row_number)
        form = ImportCustomerForm(_form_data(values))
        if not form.is_valid():
            for field_name, messages in form.errors.items():
                label = FIELD_LABELS.get(field_name, field_name)
                result.errors.append(f"แถว {row_number}: {label}: {' '.join(messages)}")
            continue

        cleaned = form.cleaned_data
        person = (cleaned["name"], cleaned["phone"], cleaned["account_number"])
        if person in existing_people:
            # Same person already saved (for example the import was run twice).
            result.skipped_existing += 1
            continue
        existing_people.add(person)
        phone = cleaned["phone"]
        if phone != MISSING and (phone in existing_phones or phone in phones_in_file):
            result.duplicate_phone_rows.append(row_number)
        phones_in_file.add(phone)
        forms.append(form)

    result.created = len(forms)
    if dry_run or not result.ok or not forms:
        if not dry_run and not result.ok:
            result.created = 0
        return result

    # Decided 2026-11-17: imported customers count as consented at import time.
    imported_at = timezone.now()
    with transaction.atomic():
        for form in forms:
            customer = form.save(commit=False)
            customer.created_by = Customer.CreatedBy.EXCEL
            customer.consent_at = imported_at
            customer.save()
        log_action(
            ActivityLog.Action.EXCEL_IMPORT,
            username="import_customers",
            details={"count": len(forms)},
        )
    return result
