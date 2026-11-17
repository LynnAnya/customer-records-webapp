"""Copy text, share text and PDF export. All data is fake."""

import io

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from audit.models import ActivityLog
from customers.pdf import build_customers_pdf
from customers.share_text import build_share_text
from customers.visibility import export_values

TEXT = reverse("customer_share_text")
PDF = reverse("customer_pdf")
PHONE = "0811112222"
ACCOUNT = "0009876543"


def logged():
    return ActivityLog.objects.exclude(action=ActivityLog.Action.LOGIN)


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    # PDF text extraction can add spaces inside Thai words; compare without them.
    return "".join(page.extract_text() for page in reader.pages).replace(" ", "")


@pytest.fixture
def somchai(make_customer):
    return make_customer(
        name="สมชาย ใจดี",
        license_plate="1กข 1234",
        phone=PHONE,
        bank_name="กสิกรไทย",
        account_number=ACCOUNT,
    )


# --- The text itself ------------------------------------------------------


def test_share_text_format(somchai, make_customer) -> None:
    mali = make_customer(
        name="มะลิ มีนา", license_plate="2ขค 99",
        bank_name="กรุงไทย", account_number="1234567890",
    )  # fmt: skip

    assert build_share_text([somchai, mali]) == (
        "ชื่อ: สมชาย ใจดี\n"
        "ทะเบียนรถ: 1กข 1234\n"
        "ธนาคาร: กสิกรไทย\n"
        f"เลขที่บัญชี: {ACCOUNT}\n"
        "\n"
        "ชื่อ: มะลิ มีนา\n"
        "ทะเบียนรถ: 2ขค 99\n"
        "ธนาคาร: กรุงไทย\n"
        "เลขที่บัญชี: 1234567890"
    )


def test_exports_never_include_phone_or_referral(somchai) -> None:
    labels = [label for label, _value in export_values(somchai)]
    values = [value for _label, value in export_values(somchai)]

    assert labels == ["ชื่อ", "ทะเบียนรถ", "ธนาคาร", "เลขที่บัญชี"]
    assert PHONE not in values


# --- Access ---------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("url", [TEXT, PDF])
def test_anonymous_users_are_sent_to_login(client, url) -> None:
    response = client.post(url, {"ids": "1", "kind": "copy"})

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.parametrize("url", [TEXT, PDF])
def test_exports_must_be_a_post(client, staff, somchai, url) -> None:
    client.force_login(staff)

    assert client.get(url, {"ids": str(somchai.pk), "kind": "copy"}).status_code == 405
    assert logged().count() == 0


# --- Copy / share text ----------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "staff"])
@pytest.mark.parametrize("kind", ["copy", "share"])
def test_text_has_full_account_number_and_no_phone(
    client, request, somchai, role, kind
) -> None:
    client.force_login(request.getfixturevalue(role))

    response = client.post(TEXT, {"ids": str(somchai.pk), "kind": kind})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert response["Cache-Control"] == "no-store"
    assert response["X-Customer-Count"] == "1"
    assert f"เลขที่บัญชี: {ACCOUNT}" in response.text
    assert "สมชาย ใจดี" in response.text
    assert PHONE not in response.text
    assert "เบอร์" not in response.text


def test_text_follows_tick_order(client, staff, make_customer) -> None:
    a, b, c = (make_customer(name=name) for name in ("หนึ่ง", "สอง", "สาม"))
    client.force_login(staff)

    text = client.post(TEXT, {"ids": f"{c.pk},{a.pk},{b.pk}", "kind": "copy"}).text

    assert text.index("สาม") < text.index("หนึ่ง") < text.index("สอง")


def test_staff_cannot_export_hidden_customers(client, staff, make_customer) -> None:
    shown = make_customer(name="มองเห็น")
    hidden = make_customer(name="ถูกซ่อน", account_number="5550001111", is_hidden=True)
    client.force_login(staff)

    response = client.post(
        TEXT, {"ids": f"{hidden.pk},{shown.pk},999999", "kind": "copy"}
    )
    pdf = client.post(PDF, {"ids": f"{hidden.pk},{shown.pk},999999"})

    assert "มองเห็น" in response.text
    assert "ถูกซ่อน" not in response.text and "5550001111" not in response.text
    assert response["X-Customer-Count"] == "1"
    assert "ถูกซ่อน" not in pdf_text(pdf.content)
    assert "5550001111" not in pdf_text(pdf.content)
    for entry in logged():
        assert entry.details["customer_ids"] == [shown.pk]


def test_admin_can_export_hidden_customers(client, admin, make_customer) -> None:
    hidden = make_customer(name="ถูกซ่อน", is_hidden=True)
    client.force_login(admin)

    assert "ถูกซ่อน" in client.post(TEXT, {"ids": str(hidden.pk), "kind": "copy"}).text


@pytest.mark.parametrize("ids", ["", "999999", "abc,-1", None])
def test_text_with_no_valid_id_returns_400_and_logs_nothing(
    client, staff, make_customer, ids
) -> None:
    make_customer(is_hidden=True)
    client.force_login(staff)
    data = {"kind": "copy"} if ids is None else {"ids": ids, "kind": "copy"}

    response = client.post(TEXT, data)

    assert response.status_code == 400
    assert logged().count() == 0


@pytest.mark.parametrize("kind", ["", "pdf", "delete"])
def test_unknown_kind_is_rejected(client, staff, somchai, kind) -> None:
    client.force_login(staff)

    response = client.post(TEXT, {"ids": str(somchai.pk), "kind": kind})

    assert response.status_code == 400
    assert ACCOUNT not in response.text
    assert logged().count() == 0


def test_text_request_needs_a_csrf_token(staff, somchai) -> None:
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    strict.force_login(staff)

    response = strict.post(TEXT, {"ids": str(somchai.pk), "kind": "copy"})

    assert response.status_code == 403
    assert logged().count() == 0


# --- PDF ------------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "staff"])
def test_pdf_download_has_thai_text_and_no_phone(
    client, request, somchai, role
) -> None:
    client.force_login(request.getfixturevalue(role))

    response = client.post(PDF, {"ids": str(somchai.pk)})

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith(
        'attachment; filename="customers-'
    )
    assert response["Cache-Control"] == "no-store"
    assert response.content.startswith(b"%PDF")
    text = pdf_text(response.content)
    for expected in ("รายชื่อลูกค้า", "สมชาย", "ใจดี", "กสิกรไทย", "1กข1234", ACCOUNT):
        assert expected in text
    assert PHONE not in text
    assert "เบอร์" not in text


def test_pdf_embeds_the_thai_font(somchai) -> None:
    content = build_customers_pdf(
        [somchai], generated_at=timezone.localtime(), generated_by="tester"
    )

    assert b"Sarabun" in content
    assert b"/FontFile2" in content  # the font program itself is inside the file


def test_pdf_works_for_one_and_for_many_customers(make_customer) -> None:
    many = [make_customer(name=f"ลูกค้า{index}") for index in range(120)]
    now = timezone.localtime()

    one = build_customers_pdf(many[:1], generated_at=now, generated_by="tester")
    big = build_customers_pdf(many, generated_at=now, generated_by="tester")

    assert len(PdfReader(io.BytesIO(one)).pages) == 1
    assert len(PdfReader(io.BytesIO(big)).pages) > 1
    assert "ลูกค้า119" in pdf_text(big)


def test_pdf_with_no_valid_id_goes_back_and_logs_nothing(client, staff) -> None:
    client.force_login(staff)

    response = client.post(PDF, {"ids": "999999"})

    assert response.status_code == 302
    assert response.url == reverse("customer_list")
    assert logged().count() == 0


def test_pdf_treats_customer_text_as_plain_text(client, staff, make_customer) -> None:
    hostile = make_customer(name='<img src="http://evil.example/x.png"> <svg>')
    client.force_login(staff)

    response = client.post(PDF, {"ids": str(hostile.pk)})

    assert response.status_code == 200
    assert "<img" in pdf_text(response.content)  # printed as letters, not loaded
    assert b"/Subtype /Image" not in response.content


# --- Activity log ---------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "extra", "action"),
    [
        (TEXT, {"kind": "copy"}, "copy"),
        (TEXT, {"kind": "share"}, "share"),
        (PDF, {}, "pdf_export"),
    ],
)
def test_each_export_writes_exactly_one_safe_log_row(
    client, staff, somchai, make_customer, url, extra, action
) -> None:
    other = make_customer(name="มะลิ")
    client.force_login(staff)

    client.post(url, {"ids": f"{somchai.pk},{other.pk}", **extra})

    entry = logged().get()
    assert entry.action == action
    assert entry.user == staff
    assert entry.details["customer_ids"] == [somchai.pk, other.pk]
    assert entry.details["count"] == 2
    assert set(entry.details) == {"customer_ids", "customer_names", "count"}
    for secret in (PHONE, ACCOUNT, "0001234567", "0800000000"):
        assert secret not in str(entry.details)


def test_no_data_leaves_if_the_log_row_cannot_be_written(
    client, staff, somchai, monkeypatch
) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("log is down")

    monkeypatch.setattr("customers.services.log_action", broken)
    client.force_login(staff)
    client.raise_request_exception = False

    response = client.post(TEXT, {"ids": str(somchai.pk), "kind": "copy"})

    assert response.status_code == 500
    assert ACCOUNT not in response.text


# --- Buttons --------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "staff"])
def test_both_roles_get_copy_share_and_pdf_buttons(
    client, request, somchai, role
) -> None:
    client.force_login(request.getfixturevalue(role))

    page = client.get(reverse("customer_list")).text

    assert TEXT in page and PDF in page
    for label in ("คัดลอก", "แชร์", "PDF"):
        assert label in page
