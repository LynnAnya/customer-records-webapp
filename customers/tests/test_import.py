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

HEADERS = ["ชื่อ", "นามสกุล", "ทะเบียนรถ", "เบอร์โทรศัพท์", "ธนาคาร", "เลขที่บัญชี", "ผู้แนะนำ"]
SOMCHAI = ["สมชาย", "ใจดี", "1กข 1234", "0811112222", "กสิกรไทย", "0001234567", ""]
MALI = ["มะลิ", "มีนา", "2ขค 99", "0822223333", "กรุงไทย", "9876543210", "คุณสมศรี"]


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
    somchai = Customer.objects.get(first_name="สมชาย")
    assert somchai.created_by == Customer.CreatedBy.EXCEL
    assert somchai.account_number == "0001234567"
    assert somchai.referral == "บริษัท"
    assert somchai.is_hidden is False
    assert Customer.objects.get(first_name="มะลิ").referral == "คุณสมศรี"


def test_real_run_writes_one_log_row_with_only_a_count(excel) -> None:
    run(excel([SOMCHAI, MALI]))

    entry = ActivityLog.objects.get()
    assert entry.action == "excel_import"
    assert entry.details == {"count": 2}
    assert entry.user is None


def test_real_run_is_all_or_nothing(excel) -> None:
    bad = ["ปิติ", "", "3คง 5", "12", "ออมสิน", "abc", ""]

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
    bad = ["ปิติ", "ดี", "3คง 5", "08123", "ออมสิน", "12ab", ""]
    out = StringIO()

    with pytest.raises(CommandError) as error:
        call_command("import_customers", str(excel([SOMCHAI, bad])), stdout=out)

    output = out.getvalue()
    assert "แถว 3: เบอร์โทรศัพท์" in output
    assert "แถว 3: เลขที่บัญชี" in output
    assert "Nothing was saved" in str(error.value)
    for secret in ("08123", "12ab", "0811112222", "0001234567"):
        assert secret not in output


def test_dashes_and_spaces_in_numbers_are_removed(excel) -> None:
    row = ["สมชาย", "ใจดี", "1กข 1234", "081-111 2222", "กสิกรไทย", "000-1-23456-7", ""]

    run(excel([row]))

    saved = Customer.objects.get()
    assert saved.phone == "0811112222"
    assert saved.account_number == "0001234567"


def test_phone_stored_as_a_number_gets_its_zero_back(excel) -> None:
    row = ["สมชาย", "ใจดี", "1กข 1234", 811112222, "กสิกรไทย", "0001234567", ""]

    run(excel([row]))

    assert Customer.objects.get().phone == "0811112222"


def test_numeric_account_numbers_are_flagged_for_checking(excel) -> None:
    row = ["สมชาย", "ใจดี", "1กข 1234", "0811112222", "กสิกรไทย", 1234567, ""]

    output = run(excel([row]), "--dry-run")

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
    twin = ["ปิติ", "ดี", "3คง 5", "0822223333", "ออมสิน", "1112223334", ""]

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


def test_english_headers_and_a_single_name_column_work(excel) -> None:
    headers = ["Name", "License Plate", "Phone", "Bank", "Account Number"]
    row = ["สมชาย ใจดี มาก", "1กข 1234", "0811112222", "กสิกรไทย", "0001234567"]

    run(excel([row], headers))

    saved = Customer.objects.get()
    assert (saved.first_name, saved.last_name) == ("สมชาย", "ใจดี มาก")
    assert saved.referral == "บริษัท"


def test_extra_columns_are_ignored(excel) -> None:
    run(excel([[*SOMCHAI, "note"]], [*HEADERS, "หมายเหตุ"]))

    assert Customer.objects.count() == 1


def test_missing_columns_stop_the_import_and_list_what_was_found(excel) -> None:
    with pytest.raises(CommandError) as error:
        run(excel([["สมชาย", "0811112222"]], ["ชื่อ", "เบอร์โทร"]))

    message = str(error.value)
    assert "Missing columns" in message
    assert "เลขที่บัญชี" in message
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
