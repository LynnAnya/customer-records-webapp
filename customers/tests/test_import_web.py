"""Excel upload page for admins. Every file here is fake and built inside the test."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from audit.models import ActivityLog
from customers import import_uploads
from customers.models import Customer

pytestmark = pytest.mark.django_db

UPLOAD = reverse("customer_import")
CHECK = reverse("customer_import_check")
CONFIRM = reverse("customer_import_confirm")
DONE = reverse("customer_import_done")
TEMPLATE = reverse("customer_import_template")
LIST = reverse("customer_list")

HEADERS = ["ลำดับ", "ทะเบียนรถ", "ชื่อ", "หมายเลขบัญชี", "ธนาคาร", "เบอร์โทร"]
PHONE = "0811112222"
ACCOUNT = "0001234567"


def row(name="สมชาย ใจดี", plate="1กข 1234", account=ACCOUNT, bank="กสิกรไทย",
        phone=PHONE):  # fmt: skip
    return [1, plate, name, account, bank, phone]


def xlsx(rows: list[list], *, sheets: dict[str, list[list]] | None = None) -> bytes:
    workbook = Workbook()
    workbook.active.title = "ลูกค้า"
    workbook.active.append(HEADERS)
    for values in rows:
        workbook.active.append(values)
    for title, extra_rows in (sheets or {}).items():
        sheet = workbook.create_sheet(title)
        for values in extra_rows:
            sheet.append(values)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def upload_file(client, content: bytes, name: str = "customers.xlsx"):
    return client.post(UPLOAD, {"file": SimpleUploadedFile(name, content)})


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    folder = tmp_path / "uploads"
    monkeypatch.setattr(import_uploads, "UPLOAD_DIR", folder)
    return folder


@pytest.fixture
def admin_client(client, admin):
    client.force_login(admin)
    return client


# --- Who may use it -------------------------------------------------------

ADMIN_URLS = [
    ("get", UPLOAD),
    ("post", UPLOAD),
    ("get", CHECK),
    ("post", CONFIRM),
    ("get", DONE),
    ("get", TEMPLATE),
]


@pytest.mark.parametrize(("method", "url"), ADMIN_URLS)
def test_staff_get_403(client, staff, method, url) -> None:
    client.force_login(staff)

    assert getattr(client, method)(url).status_code == 403


@pytest.mark.parametrize(("method", "url"), ADMIN_URLS)
def test_anonymous_users_are_sent_to_login(client, method, url) -> None:
    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_confirm_refuses_get(admin_client) -> None:
    assert admin_client.get(CONFIRM).status_code == 405


def test_staff_never_see_the_excel_button(client, staff) -> None:
    client.force_login(staff)

    assert UPLOAD not in client.get(LIST).text


def test_admin_sees_the_green_excel_button_on_desktop_only(admin_client) -> None:
    page = admin_client.get(LIST).text

    assert "เพิ่มลูกค้าจาก Excel" in page
    assert f'href="{UPLOAD}" class="btn btn-excel"' in page
    # Desktop only: the wrapper is hidden below the lg breakpoint.
    wrapper_start = page.rindex("max-lg:hidden", 0, page.index(UPLOAD))
    assert page.index("<div", wrapper_start - 40) < wrapper_start


# --- Upload, check, confirm -----------------------------------------------


def test_checking_saves_nothing_and_shows_the_counts(admin_client) -> None:
    content = xlsx([row(), row(name="มะลิ", plate="2ขค 99", phone="0822223333")])

    response = upload_file(admin_client, content)
    page = admin_client.get(response.url).text

    assert response.url == CHECK
    assert Customer.objects.count() == 0
    assert not ActivityLog.objects.filter(action=ActivityLog.Action.EXCEL_IMPORT)
    assert "ยืนยันนำเข้า 2 ราย" in page


def test_confirm_saves_every_row_and_logs_who_imported(admin_client, admin) -> None:
    upload_file(admin_client, xlsx([row(), row(name="มะลิ", plate="2ขค 99")]))

    response = admin_client.post(CONFIRM, {"sheet": "ลูกค้า"})
    page = admin_client.get(response.url).text

    assert response.url == DONE
    assert "นำเข้าแล้ว 2 ราย" in page
    assert Customer.objects.filter(created_by=Customer.CreatedBy.EXCEL).count() == 2
    entry = ActivityLog.objects.get(action=ActivityLog.Action.EXCEL_IMPORT)
    assert entry.action == ActivityLog.Action.EXCEL_IMPORT
    assert entry.user == admin
    assert entry.details == {"count": 2}


def test_the_stored_file_is_deleted_after_the_import(admin_client, upload_dir) -> None:
    upload_file(admin_client, xlsx([row()]))
    assert len(list(upload_dir.glob("*.xlsx"))) == 1

    admin_client.post(CONFIRM)

    assert list(upload_dir.glob("*.xlsx")) == []
    # A second confirm (back button, double click) finds no file and saves nothing.
    again = admin_client.post(CONFIRM)
    assert again.url == UPLOAD
    assert Customer.objects.count() == 1


def test_the_result_page_shows_once(admin_client) -> None:
    upload_file(admin_client, xlsx([row()]))
    admin_client.post(CONFIRM)

    assert admin_client.get(DONE).status_code == 200
    assert admin_client.get(DONE).url == LIST


def test_empty_cells_become_a_dash_and_exact_repeats_are_skipped(
    admin_client, make_customer
) -> None:
    make_customer(name="สมชาย ใจดี", license_plate="1กข 1234", phone=PHONE,
                  bank_name="กสิกรไทย", account_number=ACCOUNT)  # fmt: skip
    rows = [
        row(),  # exact repeat of the saved customer: skipped
        row(plate="7ขข 7777"),  # same person, another car: added
        row(name="ปิติ", plate=None, bank="", phone=None, account=None),
    ]
    upload_file(admin_client, xlsx(rows))

    page = admin_client.get(CHECK).text
    admin_client.post(CONFIRM)

    assert "ยืนยันนำเข้า 2 ราย" in page
    assert Customer.objects.count() == 3
    piti = Customer.objects.get(name="ปิติ")
    assert (piti.license_plate, piti.phone, piti.account_number) == ("-", "-", "-")


def test_an_account_that_is_not_a_number_is_saved_as_a_dash_and_listed(
    admin_client,
) -> None:
    upload_file(admin_client, xlsx([row(), row(name="ปิติ", account="ยังไม่มี")]))

    page = admin_client.get(CHECK).text
    admin_client.post(CONFIRM)
    done = admin_client.get(DONE).text

    for text in (page, done):
        assert "บันทึกเป็น “-”" in text and "แถว 3" in text
        assert "ยังไม่มี" not in text
    assert Customer.objects.get(name="ปิติ").account_number == "-"


def test_a_row_error_blocks_the_import_and_names_only_row_and_column(
    admin_client,
) -> None:
    bad = row(name="ปิติ", plate="ก" * 51)
    upload_file(admin_client, xlsx([row(), bad]))

    page = admin_client.get(CHECK).text
    response = admin_client.post(CONFIRM)

    assert "แถว 3: ทะเบียนรถ" in page
    assert "ยืนยันนำเข้า" not in page
    assert "ก" * 51 not in page
    assert response.url.startswith(CHECK)
    assert Customer.objects.count() == 0
    assert not ActivityLog.objects.filter(action=ActivityLog.Action.EXCEL_IMPORT)


def test_phone_and_account_numbers_never_appear_on_the_import_pages(
    admin_client, make_customer
) -> None:
    make_customer(phone=PHONE)  # makes row 2 a duplicate phone
    upload_file(admin_client, xlsx([row(account=1234567)]))

    page = admin_client.get(CHECK).text
    admin_client.post(CONFIRM)
    done = admin_client.get(DONE).text

    for text in (page, done):
        assert "เบอร์โทรซ้ำ" in text and "0 ข้างหน้า" in text
        assert PHONE not in text and "1234567" not in text


# --- Files that cannot be used --------------------------------------------


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("customers.csv", b"a,b", ".xlsx"),
        ("customers.xls", b"old", ".xlsx"),
        ("customers.xlsx", b"", "ว่างเปล่า"),
    ],
)
def test_wrong_files_are_refused_on_the_upload_page(
    admin_client, upload_dir, name, content, message
) -> None:
    response = upload_file(admin_client, content, name)

    assert response.status_code == 200
    assert message in response.text
    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_a_file_over_5_mb_is_refused(admin_client, monkeypatch) -> None:
    monkeypatch.setattr("customers.forms.MAX_EXCEL_BYTES", 10)

    response = upload_file(admin_client, xlsx([row()]))

    assert "ใหญ่เกิน 5 MB" in response.text


def test_a_fake_xlsx_shows_a_thai_error(admin_client) -> None:
    upload_file(admin_client, b"this is not a spreadsheet")

    page = admin_client.get(CHECK).text

    assert "เปิดไฟล์นี้เป็น Excel ไม่ได้" in page
    assert "ยืนยันนำเข้า" not in page


def test_the_right_sheet_is_found_and_can_be_changed(admin_client) -> None:
    workbook = Workbook()
    workbook.active.title = "สรุป"
    workbook.active.append(["ยอดรวม", 3])
    customers = workbook.create_sheet("ลูกค้า")
    customers.append(HEADERS)
    customers.append(row())
    buffer = BytesIO()
    workbook.save(buffer)
    upload_file(admin_client, buffer.getvalue())

    found = admin_client.get(CHECK).text
    other = admin_client.get(CHECK, {"sheet": "สรุป"}).text

    assert '<option value="ลูกค้า" selected>' in found
    assert "ยืนยันนำเข้า 1 ราย" in found
    assert "ไม่มีคอลัมน์" in other and "ยืนยันนำเข้า" not in other


def test_an_old_upload_has_expired(admin_client, upload_dir, monkeypatch) -> None:
    upload_file(admin_client, xlsx([row()]))
    monkeypatch.setattr(import_uploads, "MAX_AGE_SECONDS", -1)

    response = admin_client.get(CHECK)

    assert response.url == UPLOAD
    assert list(upload_dir.glob("*.xlsx")) == []


def test_one_admin_cannot_reach_another_admins_upload(
    client, admin, django_user_model
) -> None:
    other = django_user_model.objects.create_user(
        username="admin2", password="x", is_admin=True
    )
    client.force_login(admin)
    upload_file(client, xlsx([row()]))

    client.force_login(other)
    response = client.post(CONFIRM)

    assert response.url == UPLOAD
    assert Customer.objects.count() == 0


# --- Sample file ----------------------------------------------------------


def test_the_sample_file_has_the_headers_and_text_columns(admin_client) -> None:
    response = admin_client.get(TEMPLATE)

    sheet = load_workbook(BytesIO(response.content)).active
    headers = [cell.value for cell in sheet[1]]
    assert headers == ["ทะเบียนรถ", "ชื่อ", "หมายเลขบัญชี", "ธนาคาร", "เบอร์โทร", "ผู้แนะนำ"]
    assert sheet["C2"].number_format == "@" and sheet["E2"].number_format == "@"
    assert sheet.max_row == 1001  # styled empty rows only, no customer data
    assert all(
        cell.value is None for line in sheet.iter_rows(min_row=2) for cell in line
    )
    assert "attachment" in response["Content-Disposition"]
