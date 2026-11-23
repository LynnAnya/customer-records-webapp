"""Customers page: who sees what, search, sort, pagination. All data is fake."""

import pytest
from django.urls import reverse

from customers.queries import search_customers
from customers.visibility import mask_account_number, visible_fields

LIST = reverse("customer_list")
TABLE = reverse("customer_table")
PHONE = "0811112222"
ACCOUNT = "9876543210"


def names(queryset) -> list[str]:
    return [customer.name for customer in queryset]


# --- Access ---------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("url", [LIST, TABLE])
def test_anonymous_user_is_sent_to_login(client, url) -> None:
    response = client.get(url)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


# --- Staff never see phone ------------------------------------------------


@pytest.mark.parametrize("url", [LIST, TABLE])
def test_staff_page_has_no_phone_anywhere(client, staff, make_customer, url) -> None:
    make_customer(phone=PHONE)
    client.force_login(staff)

    page = client.get(url).text

    assert "ทดสอบ" in page
    assert PHONE not in page
    assert "เบอร์โทร" not in page


@pytest.mark.parametrize("url", [LIST, TABLE])
def test_admin_page_shows_phone(client, admin, make_customer, url) -> None:
    make_customer(phone=PHONE)
    client.force_login(admin)

    page = client.get(url).text

    assert PHONE in page
    assert "เบอร์โทร" in page


def test_staff_search_by_phone_finds_nothing(client, staff, make_customer) -> None:
    make_customer(phone=PHONE)
    client.force_login(staff)

    response = client.get(TABLE, {"q": PHONE})

    assert not response.context["page"].object_list
    assert "ทดสอบ" not in response.text
    assert not search_customers(staff, PHONE[:6]).exists()


def test_admin_search_by_phone_finds_the_customer(admin, make_customer) -> None:
    make_customer(phone=PHONE)

    assert search_customers(admin, PHONE).count() == 1


def test_phone_is_only_a_visible_field_for_admins(admin, staff) -> None:
    assert "phone" in visible_fields(admin)
    assert "phone" not in visible_fields(staff)


# --- Hidden customers -----------------------------------------------------


@pytest.mark.parametrize("url", [LIST, TABLE])
def test_staff_never_get_hidden_customers(client, staff, make_customer, url) -> None:
    make_customer(name="มองเห็น")
    make_customer(name="ถูกซ่อน", is_hidden=True)
    client.force_login(staff)

    page = client.get(url).text

    assert "มองเห็น" in page
    assert "ถูกซ่อน" not in page
    assert "ซ่อน</span>" not in page


def test_staff_search_cannot_reach_hidden_customers(staff, make_customer) -> None:
    make_customer(name="ถูกซ่อน", is_hidden=True)

    assert not search_customers(staff, "ถูกซ่อน").exists()


def test_admin_sees_hidden_customers_with_a_badge(client, admin, make_customer) -> None:
    make_customer(name="ถูกซ่อน", is_hidden=True)
    client.force_login(admin)

    page = client.get(LIST).text

    assert "ถูกซ่อน" in page
    assert "ซ่อน</span>" in page


# --- Account number is masked ---------------------------------------------


def test_account_number_is_masked_in_the_page(
    client, admin, staff, make_customer
) -> None:
    make_customer(account_number=ACCOUNT)

    for user in (admin, staff):
        client.force_login(user)
        page = client.get(LIST).text

        assert ACCOUNT not in page
        assert "•••• 3210" in page


def test_mask_keeps_only_the_last_four_digits() -> None:
    assert mask_account_number("0001234567") == "•••• 4567"


# --- Search ---------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["สมชาย", "ใจดี", "สมชาย ใจดี", "1กข", "กสิกร", ACCOUNT, "3210", "คุณสมศรี", "สมช"],
)
def test_search_matches_each_visible_field(staff, make_customer, query) -> None:
    make_customer(
        name="สมชาย ใจดี",
        bank_name="กสิกรไทย",
        account_number=ACCOUNT,
        referral="คุณสมศรี",
    )
    make_customer(name="อื่น คนละคน", license_plate="9ฮฮ 9", referral="x")

    assert names(search_customers(staff, query)) == ["สมชาย ใจดี"]


def test_search_is_case_insensitive(staff, make_customer) -> None:
    make_customer(name="John")

    assert search_customers(staff, "john").count() == 1


def test_empty_search_shows_a_helpful_message(client, staff, make_customer) -> None:
    make_customer()
    client.force_login(staff)

    page = client.get(TABLE, {"q": "ไม่มีจริง"}).text

    assert "ไม่พบลูกค้าที่ตรงกับ" in page


# --- Sort -----------------------------------------------------------------


def test_default_sort_is_newest_first(staff, make_customer) -> None:
    make_customer(name="เก่า")
    make_customer(name="ใหม่")

    assert names(search_customers(staff)) == ["ใหม่", "เก่า"]
    assert names(search_customers(staff, sort="oldest")) == ["เก่า", "ใหม่"]


def test_thai_names_sort_in_thai_dictionary_order(staff, make_customer) -> None:
    # Leading vowels (เ ไ) must sort by their consonant, not after ฮ.
    for name in ["ไก่", "ขวด", "กา", "คน", "เกวียน"]:
        make_customer(name=name)

    expected = ["กา", "เกวียน", "ไก่", "ขวด", "คน"]
    assert names(search_customers(staff, sort="name_az")) == expected
    assert names(search_customers(staff, sort="name_za")) == expected[::-1]


def test_bank_sort(staff, make_customer) -> None:
    make_customer(name="b", bank_name="ไทยพาณิชย์")
    make_customer(name="a", bank_name="กรุงเทพ")

    assert names(search_customers(staff, sort="bank_az")) == ["a", "b"]


@pytest.mark.parametrize("bad_sort", ["phone", "-phone", "password", "id; drop", ""])
def test_unknown_sort_keys_fall_back_to_newest(
    client, staff, make_customer, bad_sort
) -> None:
    make_customer(name="เก่า")
    make_customer(name="ใหม่")
    client.force_login(staff)

    response = client.get(TABLE, {"sort": bad_sort})

    assert response.status_code == 200
    assert response.context["sort"] == "newest"
    assert names(response.context["page"].object_list) == ["ใหม่", "เก่า"]


# --- Pagination and the HTMX fragment -------------------------------------


def test_pagination_shows_25_per_page(client, staff, make_customer) -> None:
    for index in range(27):
        make_customer(name=f"ลูกค้า{index:02d}")
    client.force_login(staff)

    first = client.get(TABLE)
    second = client.get(TABLE, {"page": 2})
    beyond = client.get(TABLE, {"page": 99})

    assert len(first.context["page"].object_list) == 25
    assert len(second.context["page"].object_list) == 2
    assert beyond.context["page"].number == 2
    assert "หน้า 1 / 2" in first.text


def test_fragment_is_only_the_table_and_keeps_the_page_url(
    client, staff, make_customer
) -> None:
    make_customer(name="สมชาย")
    client.force_login(staff)

    response = client.get(TABLE, {"q": "สมชาย", "sort": "name_az"})

    assert "<html" not in response.text
    assert "สมชาย" in response.text
    assert response["HX-Replace-Url"].startswith(f"{LIST}?q=")
    assert "sort=name_az" in response["HX-Replace-Url"]


def test_full_page_greets_and_keeps_the_search_text(
    client, staff, make_customer
) -> None:
    client.force_login(staff)

    page = client.get(LIST, {"q": "สมชาย"}).text

    assert "สวัสดี นิสา" in page
    assert 'value="สมชาย"' in page


# --- Phone cards ----------------------------------------------------------


def test_phone_card_has_summary_details_and_a_toggle(
    client, admin, make_customer
) -> None:
    customer = make_customer(phone=PHONE, account_number=ACCOUNT)
    client.force_login(admin)

    page = client.get(TABLE).text

    assert f'aria-controls="card-details-{customer.pk}"' in page
    # Closed until the arrow is tapped, also in the HTML itself (no JavaScript yet).
    assert f'id="card-details-{customer.pk}" class="card-details" hidden' in page
    assert "วันที่เพิ่ม" in page and "ผู้แนะนำ" in page
    assert "•••• 3210" in page and ACCOUNT not in page


def test_staff_phone_card_never_has_the_phone(client, staff, make_customer) -> None:
    make_customer(phone=PHONE)
    client.force_login(staff)

    page = client.get(TABLE).text

    assert PHONE not in page
    assert "เบอร์โทร" not in page


def test_icon_only_buttons_keep_thai_labels(client, admin, make_customer) -> None:
    customer = make_customer(name="สมชาย")
    client.force_login(admin)

    page = client.get(LIST).text

    for label in ("แก้ไข สมชาย", "ซ่อน สมชาย", "คัดลอก สมชาย", "แชร์ สมชาย"):
        assert f'aria-label="{label}"' in page
    assert 'aria-label="ลบ สมชาย"' not in page  # delete: selection bar only
    for word in ("คัดลอก", "PDF", "ซ่อน", "แสดง", "ลบ"):
        assert f'<span class="bar-label">{word}</span>' in page
    assert customer.pk


def test_desktop_table_has_separate_bank_and_account_columns(
    client, staff, make_customer
) -> None:
    make_customer(bank_name="กรุงไทย", account_number=ACCOUNT)
    client.force_login(staff)

    page = client.get(TABLE).text

    assert "ธนาคาร / บัญชี" not in page
    assert '<th scope="col">เลขที่บัญชี</th>' in page
    assert "<td>กรุงไทย</td>" in page
    assert '<td class="tabular-nums whitespace-nowrap">•••• 3210</td>' in page
    assert ACCOUNT not in page


# --- Injection: customer text is only ever plain text ---------------------

ATTACKS = [
    "'); alert('x'); ('",
    "<img src=x onerror=alert(1)>",
    '" x-init="alert(1)" @click="alert(2)',
    "<script>alert(3)</script>",
]


def alpine_attribute_values(page: str) -> list[str]:
    """Values of attributes Alpine runs as code: x-*, @event, :binding."""
    import re

    pattern = r'\s(?:x-[\w:.-]+|@[\w:.-]+|:[\w-]+)\s*=\s*"([^"]*)"'
    return re.findall(pattern, page)


@pytest.mark.parametrize("attack", ATTACKS)
@pytest.mark.parametrize("role", ["admin", "staff"])
def test_customer_text_never_becomes_code(
    client, request, make_customer, role, attack
) -> None:
    customer = make_customer(name=attack, license_plate=attack[:40], referral=attack)
    client.force_login(request.getfixturevalue(role))

    page = client.get(LIST, {"selected": str(customer.pk)}).text

    # Escaped as text: no new tags, no broken-out attributes.
    assert "<img src=x" not in page and "<script>alert" not in page
    assert 'x-init="alert(1)"' not in page
    # Alpine code on the page never contains customer text, only ids and counts.
    for value in alpine_attribute_values(page):
        assert "alert" not in value


def test_table_refreshes_never_add_back_button_entries(client, staff) -> None:
    client.force_login(staff)

    response = client.get(TABLE, {"q": "x"})

    assert "HX-Push-Url" not in response
    assert response["HX-Replace-Url"].startswith(f"{LIST}?q=x")
