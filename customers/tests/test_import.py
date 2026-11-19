"""Excel import command. Every file here is fake and built inside the test."""

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from openpyxl import Workbook

from audit.models import ActivityLog
from customers.importing import import_customers
from customers.models import Customer

pytestmark = pytest.mark.django_db

# The client's real header row (row 1), with an extra referral column for tests.
HEADERS = ["ลำดับ", "ทะเบียนรถ", "ชื่อ", "หมายเลขบัญชี", "ธนาคาร", "เบอร์โทร", "ผู้แนะนำ"]
SOMCHAI = [1, "1กข 1234", "สมชาย ใจดี", "0001234567", "กสิกรไทย", "0811112222", ""]
MALI = [2, "2ขค 99", "มะลิ มีนา", "9876543210", "กรุงไทย", "0822223333", "คุณสมศรี"]


def row(*, plate="1กข 1234", name="สมชาย ใจดี", account="0001234567",
        bank="กสิกรไทย", phone="0811112222", referral=""):  # fmt: skip
    return [1, plate, name, account, bank, phone, referral]


@pytest.fixture
def excel(tmp_path):
    def _build(rows: list[list], headers: list[str] | None = None) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers or HEADERS)
        for row in rows:
            sheet.append(row)
        path = tmp_path / "customers.xlsx"
        workbook.save(path)
        return path

    return _build


def run(path: Path, *flags: str) -> str:
    out = StringIO()
    call_command("import_customers", str(path), *flags, stdout=out)
    return out.getvalue()


# --- Dry run and real run -------------------------------------------------


def test_dry_run_writes_nothing(excel) -> None:
    output = run(excel([SOMCHAI, MALI]), "--dry-run")

    assert Customer.objects.count() == 0
    assert ActivityLog.objects.count() == 0
    assert "2 customers would be imported" in output


def test_real_run_saves_customers_as_excel(excel) -> None:
    output = run(excel([SOMCHAI, MALI]))

    assert "Imported 2 customers" in output
    somchai = Customer.objects.get(name="สมชาย ใจดี")
    assert somchai.created_by == Customer.CreatedBy.EXCEL
    assert somchai.account_number == "0001234567"
    assert somchai.referral == "บริษัท"
    assert somchai.is_hidden is False
    assert Customer.objects.get(name="มะลิ มีนา").referral == "คุณสมศรี"


def test_real_run_writes_one_log_row_with_only_a_count(excel) -> None:
    run(excel([SOMCHAI, MALI]))

    entry = ActivityLog.objects.get()
    assert entry.action == "excel_import"
    assert entry.details == {"count": 2}
    assert entry.user is None


def test_real_run_is_all_or_nothing(excel) -> None:
    bad = row(name="ปิติ", account="abc")

    with pytest.raises(CommandError):
        run(excel([SOMCHAI, bad, MALI]))

    assert Customer.objects.count() == 0
    assert ActivityLog.objects.count() == 0


def test_a_failure_while_saving_rolls_everything_back(excel, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("log is down")

    monkeypatch.setattr("customers.importing.log_action", broken)

    with pytest.raises(RuntimeError):
        import_customers(excel([SOMCHAI, MALI]), dry_run=False)

    assert Customer.objects.count() == 0


# --- Same rules as the forms ----------------------------------------------


def test_errors_name_the_row_and_column_without_the_values(excel) -> None:
    bad = row(name="ปิติ", account="12ab", phone="08123")
    out = StringIO()

    with pytest.raises(CommandError) as error:
        call_command("import_customers", str(excel([SOMCHAI, bad])), stdout=out)

    output = out.getvalue()
    assert "แถว 3: หมายเลขบัญชี" in output
    assert "Nothing was saved" in str(error.value)
    for secret in ("08123", "12ab", "0811112222", "0001234567"):
        assert secret not in output


def test_dashes_and_spaces_in_numbers_are_removed(excel) -> None:
    run(excel([row(phone="081-111 2222", account="000-1-23456-7")]))

    saved = Customer.objects.get()
    assert saved.phone == "0811112222"
    assert saved.account_number == "0001234567"


def test_phone_stored_as_a_number_gets_its_zero_back(excel) -> None:
    run(excel([row(phone=811112222)]))

    assert Customer.objects.get().phone == "0811112222"


def test_numeric_account_numbers_are_flagged_for_checking(excel) -> None:
    output = run(excel([row(account=1234567)]), "--dry-run")

    assert "leading 0" in output
    assert "as Text: 2" in output
    assert "1234567" not in output


def test_blank_rows_are_skipped(excel) -> None:
    blank = [None] * 7

    output = run(excel([SOMCHAI, blank, MALI, blank]))

    assert "Rows read: 2" in output
    assert Customer.objects.count() == 2


# --- Duplicates -----------------------------------------------------------


def test_duplicate_phones_are_imported_and_flagged(excel, make_customer) -> None:
    make_customer(phone="0811112222")
    twin = row(name="ปิติ ดี", phone="0822223333", account="1112223334")

    output = run(excel([SOMCHAI, MALI, twin]))

    assert Customer.objects.count() == 4
    assert "Phone already used" in output
    assert "rows: 2, 4" in output
    assert "0811112222" not in output


def test_running_the_same_file_twice_does_not_double_the_customers(excel) -> None:
    path = excel([SOMCHAI, MALI])
    run(path)

    output = run(path)

    assert Customer.objects.count() == 2
    assert "skipped): 2" in output
    assert ActivityLog.objects.count() == 1


# --- Headers and files ----------------------------------------------------


def test_english_headers_work_and_referral_defaults(excel) -> None:
    headers = ["Name", "License Plate", "Phone", "Bank", "Account Number"]
    values = ["สมชาย ใจดี", "1กข 1234", "0811112222", "กสิกรไทย", "0001234567"]

    run(excel([values], headers))

    saved = Customer.objects.get()
    assert saved.name == "สมชาย ใจดี"
    assert saved.referral == "บริษัท"


def test_empty_cells_are_saved_as_a_dash(excel) -> None:
    run(excel([row(plate=None, account=None, bank="", phone=None)]))

    saved = Customer.objects.get()
    assert saved.name == "สมชาย ใจดี"
    for field in ("license_plate", "account_number", "bank_name", "phone"):
        assert getattr(saved, field) == "-", field


def test_phone_text_is_kept_as_written(excel) -> None:
    run(excel([row(phone="ใช้เบอร์ John")]))

    assert Customer.objects.get().phone == "ใช้เบอร์ John"


def test_rows_without_a_phone_are_not_flagged_as_duplicates(excel) -> None:
    output = run(excel([row(phone=None), row(name="ปิติ", phone=None)]))

    assert Customer.objects.count() == 2
    assert "Phone already used" not in output


def test_extra_columns_are_ignored(excel) -> None:
    run(excel([[*SOMCHAI, "note"]], [*HEADERS, "หมายเหตุ"]))

    assert Customer.objects.count() == 1


def test_missing_columns_stop_the_import_and_list_what_was_found(excel) -> None:
    with pytest.raises(CommandError) as error:
        run(excel([["สมชาย", "0811112222"]], ["ชื่อ", "เบอร์โทร"]))

    message = str(error.value)
    assert "Missing columns" in message
    assert "หมายเลขบัญชี" in message
    assert "Headers found: ชื่อ, เบอร์โทร" in message
    assert Customer.objects.count() == 0


@pytest.mark.parametrize("name", ["missing.xlsx", "customers.csv"])
def test_wrong_or_missing_file_is_a_clear_error(tmp_path, name) -> None:
    path = tmp_path / name
    if name.endswith(".csv"):
        path.write_text("a,b")

    with pytest.raises(CommandError):
        run(path)


def test_a_file_that_is_not_really_excel_is_a_clear_error(tmp_path) -> None:
    path = tmp_path / "fake.xlsx"
    path.write_text("this is not a spreadsheet")

    with pytest.raises(CommandError):
        run(path)
