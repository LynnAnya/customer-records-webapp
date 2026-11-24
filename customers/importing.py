"""Read customers from an Excel file and save them. Used by `import_customers`.

Used by the `import_customers` command and by the admin's Excel upload page.

Every row goes through `ImportCustomerForm`: the same rules as the app forms,
except that empty cells are allowed and saved as "-", and an account number
that is not a number is saved as "-" and listed for checking. Nothing here
prints or returns a phone or account number: problems are reported by row and
column.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from openpyxl import load_workbook

from audit.models import ActivityLog
from audit.services import log_action
from customers.forms import ImportCustomerForm
from customers.models import MISSING, Customer, is_no_data

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
# A row is skipped only when ALL of these match a saved customer or an earlier
# row (an exact repeat, e.g. the file imported twice). The same person with
# another plate, bank or account is a separate row: one person may have many
# cars (decided by the user, 2026-11-22). Referral is left out on purpose: it
# is not in the client's file and an admin may change it later.
MATCH_FIELDS = ("name", "license_plate", "phone", "bank_name", "account_number")
# A bigger file is refused: the client's whole list is a few hundred rows.
MAX_ROWS = 5000
# The same rule as the forms: digits only after removing spaces and dashes.
ACCOUNT_DIGITS = re.compile(r"\d{1,20}")


class ImportFileError(Exception):
    """The file cannot be used at all (missing, wrong type, wrong headers).

    `str(error)` is English for the terminal command; `thai` is shown on the
    upload page. `sheet_names` lets the page offer another sheet.
    """

    def __init__(self, message: str, thai: str, sheet_names: list[str] | None = None):
        super().__init__(message)
        self.thai = thai
        self.sheet_names = sheet_names or []


@dataclass
class ImportResult:
    rows_read: int = 0
    created: int = 0
    skipped_duplicates: int = 0
    duplicate_phone_rows: list[int] = field(default_factory=list)
    numeric_account_rows: list[int] = field(default_factory=list)
    invalid_account_rows: list[int] = field(default_factory=list)
    sheet_name: str = ""
    sheet_names: list[str] = field(default_factory=list)
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


def _columns(header_row: tuple) -> list[str]:
    return [HEADER_ALIASES.get(_header_key(cell), "") for cell in header_row]


def _missing(columns: list[str]) -> list[str]:
    found = {name for name in columns if name}
    return [FIELD_LABELS[name] for name in REQUIRED_FIELDS if name not in found]


@dataclass
class _Sheet:
    name: str
    names: list[str]
    rows: list[tuple[int, dict[str, object]]]


def _read_rows(path: Path, sheet: str | None = None) -> _Sheet:
    """Read the chosen sheet, or else the first sheet that has every column.

    Returns (Excel row number, raw values) for every row that is not blank.
    """
    if not path.is_file():
        raise ImportFileError(f"File not found: {path}", "ไม่พบไฟล์ กรุณาอัปโหลดใหม่")
    if path.suffix.lower() != ".xlsx":
        raise ImportFileError(
            "The file must be an .xlsx Excel file.",
            "ไฟล์ต้องเป็น Excel นามสกุล .xlsx",
        )
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises several unrelated types
        raise ImportFileError(
            "The file could not be opened as Excel.",
            "เปิดไฟล์นี้เป็น Excel ไม่ได้ กรุณาบันทึกเป็น .xlsx จาก Excel แล้วลองใหม่",
        ) from error

    names = list(workbook.sheetnames)
    rows = None
    try:
        if sheet is not None and sheet not in names:
            raise ImportFileError(
                f"No sheet named {sheet!r}.", "ไม่พบแท็บที่เลือกในไฟล์นี้", names
            )
        candidates = [sheet] if sheet is not None else names
        first_problem: ImportFileError | None = None
        for name in candidates:
            rows = workbook[name].iter_rows(values_only=True)
            header_row = next(rows, None)
            columns = _columns(header_row or ())
            missing = _missing(columns)
            if not missing:
                return _Sheet(name, names, _data_rows(columns, rows))
            if first_problem is None:
                first_problem = _missing_columns_error(name, header_row, missing, names)
            rows.close()
            rows = None
        raise first_problem or ImportFileError(
            "The file has no sheets.", "ไฟล์นี้ไม่มีแท็บข้อมูล", names
        )
    finally:
        # A half-read sheet (stopped by an error) holds part of the file open,
        # and closing the workbook alone does not release it. Close it first.
        if rows is not None:
            rows.close()
        workbook.close()


def _missing_columns_error(
    name: str, header_row: tuple | None, missing: list[str], names: list[str]
) -> ImportFileError:
    if not header_row or not any(header_row):
        return ImportFileError(
            f"The sheet {name!r} is empty.", f"แท็บ “{name}” ไม่มีข้อมูล", names
        )
    seen = ", ".join(str(cell) for cell in header_row if cell) or "(none)"
    where = "" if len(names) == 1 else f" (sheet {name!r})"
    return ImportFileError(
        f"Missing columns{where}: {', '.join(missing)}. Headers found: {seen}",
        f"แท็บ “{name}” ไม่มีคอลัมน์: {', '.join(missing)} (หัวคอลัมน์ในแถวแรกคือ: {seen})",
        names,
    )


def _data_rows(columns: list[str], rows) -> list[tuple[int, dict[str, object]]]:
    data: list[tuple[int, dict[str, object]]] = []
    for row_number, row in enumerate(rows, start=2):
        # Rows can be shorter than the header row; missing cells are blank.
        cells = zip(columns, row, strict=False)
        values = {name: cell for name, cell in cells if name}
        if any(_cell_text(cell) for cell in values.values()):
            data.append((row_number, values))
            if len(data) > MAX_ROWS:
                raise ImportFileError(
                    f"More than {MAX_ROWS} rows. Split the file.",
                    f"ไฟล์มีข้อมูลเกิน {MAX_ROWS:,} แถว กรุณาแบ่งเป็นหลายไฟล์",
                )
    return data


def _match_key(values: tuple[str, ...]) -> tuple[str, ...]:
    """Values compared to find exact repeats. "-", 0 and an empty cell all mean
    "no data yet", so a saved customer whose "-" an admin changed to 0 still
    matches the Excel row (decided by the user, 2026-11-24)."""
    return tuple(
        MISSING if not value or is_no_data(value) else value for value in values
    )


def _account_is_valid(text: str) -> bool:
    """Empty, "-" or digits once spaces and dashes are removed (as the form)."""
    digits = re.sub(r"[\s-]", "", text)
    return not digits or bool(ACCOUNT_DIGITS.fullmatch(digits))


def _form_data(values: dict[str, object]) -> dict[str, str]:
    data = {name: _cell_text(cell) for name, cell in values.items()}
    data["phone"] = _phone_text(values.get("phone"))
    data.setdefault("referral", "")
    return data


def import_customers(
    path: Path,
    *,
    dry_run: bool,
    sheet: str | None = None,
    user=None,
    ip_address: str | None = None,
) -> ImportResult:
    """Validate every row, then save all of them or none.

    `dry_run=True` checks everything and writes nothing. A real run is one
    transaction: any invalid row stops the import with nothing saved.
    `sheet=None` uses the first sheet that has every required column.
    `user` is the admin who uploaded the file (None for the terminal command).
    """
    read = _read_rows(path, sheet)
    rows = read.rows
    result = ImportResult(
        rows_read=len(rows),
        dry_run=dry_run,
        sheet_name=read.name,
        sheet_names=read.names,
    )

    existing_phones = set(Customer.objects.values_list("phone", flat=True))
    seen_rows = {_match_key(row) for row in Customer.objects.values_list(*MATCH_FIELDS)}
    phones_in_file: set[str] = set()
    forms: list[ImportCustomerForm] = []

    for row_number, values in rows:
        if isinstance(values.get("account_number"), int | float):
            result.numeric_account_rows.append(row_number)
        data = _form_data(values)
        if not _account_is_valid(data.get("account_number", "")):
            # Letters or a note: the row is still imported, with "-" (decided
            # by the user, 2026-11-24), and listed so the admin can call.
            data["account_number"] = ""
            result.invalid_account_rows.append(row_number)
        form = ImportCustomerForm(data)
        if not form.is_valid():
            for field_name, messages in form.errors.items():
                label = FIELD_LABELS.get(field_name, field_name)
                result.errors.append(f"แถว {row_number}: {label}: {' '.join(messages)}")
            continue

        cleaned = form.cleaned_data
        values = _match_key(tuple(cleaned[name] for name in MATCH_FIELDS))
        if values in seen_rows:
            # Exact repeat of a saved customer or an earlier row.
            result.skipped_duplicates += 1
            continue
        seen_rows.add(values)
        phone = cleaned["phone"]
        if not is_no_data(phone) and (
            phone in existing_phones or phone in phones_in_file
        ):
            result.duplicate_phone_rows.append(row_number)
        phones_in_file.add(phone)
        forms.append(form)

    result.created = len(forms)
    if dry_run or not result.ok or not forms:
        if not dry_run and not result.ok:
            result.created = 0
        return result

    with transaction.atomic():
        for form in forms:
            customer = form.save(commit=False)
            customer.created_by = Customer.CreatedBy.EXCEL
            customer.save()
        log_action(
            ActivityLog.Action.EXCEL_IMPORT,
            user=user,
            username="" if user else "import_customers",
            details={"count": len(forms)},
            ip_address=ip_address,
        )
    return result
