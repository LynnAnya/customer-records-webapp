"""Customers page: filters, tick-to-pin selection, polling. All data is fake."""

from datetime import timedelta

import pytest
from django.http import QueryDict
from django.urls import reverse
from django.utils import timezone

from customers.filters import (
    bank_choices,
    parse_filters,
    parse_selected_ids,
    referral_choices,
)
from customers.models import Customer
from customers.queries import pinned_customers, search_customers, visible_customers

LIST = reverse("customer_list")
TABLE = reverse("customer_table")


def names(customers) -> list[str]:
    return [customer.name for customer in customers]


@pytest.fixture
def params():
    def _build(**values) -> QueryDict:
        query = QueryDict(mutable=True)
        query.update(values)
        return query

    return _build


# --- Filters --------------------------------------------------------------


def test_admin_can_filter_by_source(admin, make_customer, params) -> None:
    make_customer(name="qr", created_by=Customer.CreatedBy.QR_CODE)
    make_customer(name="excel", created_by=Customer.CreatedBy.EXCEL)

    filters = parse_filters(params(source="excel"), admin)

    assert names(search_customers(admin, filters=filters)) == ["excel"]


def test_staff_have_no_source_filter(client, staff, make_customer, params) -> None:
    make_customer(name="qr", created_by=Customer.CreatedBy.QR_CODE)
    make_customer(name="excel", created_by=Customer.CreatedBy.EXCEL)
    client.force_login(staff)

    filters = parse_filters(params(source="excel"), staff)

    assert filters.source == "" and filters.active_count == 0
    assert len(client.get(TABLE, {"source": "excel"}).context["page"]) == 2
    assert 'name="source"' not in client.get(LIST).text


def test_name_filter_follows_the_first_consonant(staff, make_customer, params) -> None:
    for name in ("นก", "นนทรี", "เนเน่", "แน่น", "โน้ต", "ไก่", "สมนึก", "Nok"):
        make_customer(name=name)

    def found(value: str) -> list[str]:
        filters = parse_filters(params(name=value), staff)
        return names(search_customers(staff, sort="name_az", filters=filters))

    # Same grouping and order as the Thai dictionary sort.
    assert found("น") == ["นก", "นนทรี", "เนเน่", "แน่น", "โน้ต"]
    assert found("นน") == ["นนทรี"]
    assert found("เน") == ["เนเน่"]  # typed with a vowel: matched as typed
    assert found("ก") == ["ไก่"]
    assert found("nok") == ["Nok"]  # any letter case


def test_name_filter_treats_symbols_as_plain_text(staff, make_customer, params) -> None:
    make_customer(name="a.b")
    make_customer(name="axb")

    filters = parse_filters(params(name="a."), staff)

    assert names(search_customers(staff, filters=filters)) == ["a.b"]


def test_plate_filter_matches_anywhere_in_the_plate(
    staff, make_customer, params
) -> None:
    make_customer(name="a", license_plate="1กข 1234")
    make_customer(name="b", license_plate="9ฮฮ 5678")

    filters = parse_filters(params(plate="กข"), staff)

    assert names(search_customers(staff, filters=filters)) == ["a"]


def test_bank_filter_is_exact_and_ignores_case(staff, make_customer, params) -> None:
    make_customer(name="a", bank_name="กสิกรไทย")
    make_customer(name="b", bank_name="กสิกรไทย สาขาสยาม")
    make_customer(name="c", bank_name="KBank")

    def found(value: str) -> list[str]:
        filters = parse_filters(params(bank=value), staff)
        return names(search_customers(staff, sort="oldest", filters=filters))

    assert found("กสิกรไทย") == ["a"]
    assert found("kbank") == ["c"]


def test_field_filters_combine_and_count(staff, make_customer, params) -> None:
    make_customer(name="ทองดี", bank_name="กสิกรไทย", license_plate="1กข 1")
    make_customer(name="ทองคำ", bank_name="ออมสิน", license_plate="1กข 2")
    make_customer(name="มานี", bank_name="กสิกรไทย", license_plate="1กข 3")

    filters = parse_filters(params(name="ท", bank="กสิกรไทย", plate="กข"), staff)

    assert names(search_customers(staff, filters=filters)) == ["ทองดี"]
    assert filters.active_count == 3


def test_bank_dropdown_never_lists_banks_of_hidden_customers_for_staff(
    staff, admin, make_customer
) -> None:
    make_customer(bank_name="กสิกรไทย")
    make_customer(bank_name="ธนาคารลับ", is_hidden=True)

    assert bank_choices(visible_customers(staff)) == ["กสิกรไทย"]
    assert set(bank_choices(visible_customers(admin))) == {"กสิกรไทย", "ธนาคารลับ"}


def test_field_filters_never_search_phone(staff, make_customer, params) -> None:
    make_customer(name="ทดสอบ", phone="0812345678", license_plate="1กข 1")

    filters = parse_filters(params(plate="0812", name="0812"), staff)

    assert search_customers(staff, filters=filters).count() == 0


def test_filter_by_referral_ignores_letter_case(staff, make_customer, params) -> None:
    make_customer(name="a", referral="Facebook")
    make_customer(name="b", referral="facebook")
    make_customer(name="c", referral="คุณสมศรี")

    filters = parse_filters(params(referral="FACEBOOK"), staff)

    assert names(search_customers(staff, sort="oldest", filters=filters)) == ["a", "b"]


def test_filter_by_date_range(staff, make_customer, params) -> None:
    today = timezone.localdate()
    old = make_customer(name="old")
    Customer.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    make_customer(name="new")

    since = parse_filters(params(**{"from": str(today - timedelta(days=1))}), staff)
    until = parse_filters(params(to=str(today - timedelta(days=5))), staff)

    assert names(search_customers(staff, filters=since)) == ["new"]
    assert names(search_customers(staff, filters=until)) == ["old"]


def test_admin_can_filter_hidden_or_visible(admin, make_customer, params) -> None:
    make_customer(name="shown")
    make_customer(name="hidden", is_hidden=True)

    only_hidden = parse_filters(params(hidden="hidden"), admin)
    only_visible = parse_filters(params(hidden="visible"), admin)

    assert names(search_customers(admin, filters=only_hidden)) == ["hidden"]
    assert names(search_customers(admin, filters=only_visible)) == ["shown"]


def test_staff_cannot_use_the_hidden_filter(
    client, staff, make_customer, params
) -> None:
    make_customer(name="มองเห็น")
    make_customer(name="ถูกซ่อน", is_hidden=True)
    client.force_login(staff)

    assert parse_filters(params(hidden="hidden"), staff).hidden == ""
    page = client.get(TABLE, {"hidden": "hidden"}).text
    assert "ถูกซ่อน" not in page
    assert "มองเห็น" in page
    assert 'name="hidden"' not in client.get(LIST).text


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "phone"},
        {"from": "not-a-date"},
        {"to": "2026-13-45"},
        {"hidden": "everything"},
    ],
)
def test_invalid_filter_values_are_ignored(client, admin, make_customer, bad) -> None:
    make_customer()
    client.force_login(admin)

    response = client.get(TABLE, bad)

    assert response.status_code == 200
    assert response.context["filters"].active_count == 0
    assert len(response.context["page"].object_list) == 1


def test_filters_combine_with_search(admin, make_customer, params) -> None:
    make_customer(name="สมชาย", created_by=Customer.CreatedBy.QR_CODE)
    make_customer(name="สมชาย", created_by=Customer.CreatedBy.EXCEL)

    filters = parse_filters(params(source="qr_code"), admin)

    assert search_customers(admin, "สมชาย", filters=filters).count() == 1


def test_referral_dropdown_lists_each_spelling_once(staff, make_customer) -> None:
    make_customer(referral="Facebook")
    make_customer(referral="facebook")
    make_customer(referral="")

    choices = referral_choices(visible_customers(staff))

    assert len(choices) == 2
    assert "บริษัท" in choices


def test_staff_referral_dropdown_hides_referrals_of_hidden_customers(
    admin, staff, make_customer
) -> None:
    make_customer(referral="ความลับ", is_hidden=True)

    assert "ความลับ" not in referral_choices(visible_customers(staff))
    assert "ความลับ" in referral_choices(visible_customers(admin))


# --- Selection: ticked rows are pinned ------------------------------------


def test_selected_ids_parser_keeps_order_and_drops_rubbish() -> None:
    assert parse_selected_ids("5,2,9,2,abc,-1,,3.5, 7,٣") == [5, 2, 9]
    assert parse_selected_ids("") == []
    assert parse_selected_ids(None) == []


def test_pinned_rows_come_first_in_tick_order(client, staff, make_customer) -> None:
    a, b, c = (make_customer(name=name) for name in "abc")
    client.force_login(staff)

    response = client.get(TABLE, {"selected": f"{a.pk},{c.pk}"})

    assert names(response.context["pinned"]) == ["a", "c"]
    assert names(response.context["page"].object_list) == ["b"]
    assert response.text.index(f'data-row-id="{a.pk}"') < response.text.index(
        f'data-row-id="{b.pk}"'
    )


def test_pinned_rows_are_not_repeated_in_the_results(
    client, staff, make_customer
) -> None:
    a = make_customer(name="a")
    make_customer(name="b")
    client.force_login(staff)

    response = client.get(TABLE, {"selected": str(a.pk)})

    all_rows = response.context["pinned"] + list(response.context["page"].object_list)
    assert len(all_rows) == len({customer.pk for customer in all_rows}) == 2


def test_pinned_rows_survive_a_search_that_does_not_match_them(
    client, staff, make_customer
) -> None:
    pinned = make_customer(name="ปักหมุด")
    make_customer(name="สมชาย")
    client.force_login(staff)

    response = client.get(TABLE, {"q": "สมชาย", "selected": str(pinned.pk)})

    assert names(response.context["pinned"]) == ["ปักหมุด"]
    assert names(response.context["page"].object_list) == ["สมชาย"]


def test_pinned_rows_survive_page_changes_and_do_not_use_page_slots(
    client, staff, make_customer
) -> None:
    customers = [make_customer(name=f"c{index:02d}") for index in range(28)]
    pinned_ids = f"{customers[0].pk},{customers[1].pk}"
    client.force_login(staff)

    first = client.get(TABLE, {"selected": pinned_ids})
    second = client.get(TABLE, {"selected": pinned_ids, "page": 2})

    for response in (first, second):
        assert names(response.context["pinned"]) == ["c00", "c01"]
    assert len(first.context["page"].object_list) == 25
    assert len(second.context["page"].object_list) == 1


def test_staff_cannot_pin_a_hidden_customer(
    client, staff, admin, make_customer
) -> None:
    hidden = make_customer(name="ถูกซ่อน", is_hidden=True)
    client.force_login(staff)

    response = client.get(TABLE, {"selected": f"{hidden.pk},999999"})

    assert response.context["pinned"] == []
    assert "ถูกซ่อน" not in response.text
    assert f'data-dropped="{hidden.pk},999999"' in response.text
    assert names(pinned_customers(admin, [hidden.pk])[0]) == ["ถูกซ่อน"]


def test_unticking_puts_the_row_back_in_the_results(
    client, staff, make_customer
) -> None:
    a = make_customer(name="a")
    client.force_login(staff)

    response = client.get(TABLE, {"selected": ""})

    assert response.context["pinned"] == []
    assert names(response.context["page"].object_list) == ["a"]
    assert Customer.objects.filter(pk=a.pk).exists()


# --- Polling keeps the user's state ---------------------------------------


def test_polling_url_keeps_search_sort_filters_and_page(
    client, admin, make_customer
) -> None:
    for index in range(27):
        make_customer(name=f"สมชาย{index}", created_by=Customer.CreatedBy.EXCEL)
    client.force_login(admin)

    state = {
        "q": "สมชาย",
        "sort": "name_az",
        "source": "excel",
        "page": 2,
        "selected": "1",
    }
    page = client.get(TABLE, state).text

    assert 'hx-trigger="every 10s' in page
    poll_url = page.split('hx-get="')[1].split('"')[0]
    for part in ("sort=name_az", "source=excel", "page=2", "q="):
        assert part in poll_url
    # Ticked IDs are sent from the browser's own list, not copied into URLs.
    assert "selected" not in poll_url
    assert 'hx-include="#selected-ids"' in page


def test_address_bar_url_never_contains_selected_ids(
    client, admin, make_customer
) -> None:
    a = make_customer()
    client.force_login(admin)

    response = client.get(TABLE, {"selected": str(a.pk), "source": "admin"})

    assert "selected" not in response["HX-Push-Url"]
    assert "source=admin" in response["HX-Push-Url"]
