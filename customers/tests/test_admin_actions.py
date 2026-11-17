"""Admin actions: add, edit, delete, hide/unhide. All data is fake."""

from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from audit.models import ActivityLog
from customers.models import Customer

LIST = reverse("customer_list")
CREATE = reverse("customer_create")
HIDE = reverse("customer_set_hidden")
PHONE = "0811112222"
ACCOUNT = "9876543210"


def form_data(**overrides) -> dict[str, str]:
    data = {
        "name": "สมชาย ใจดี",
        "license_plate": "1กข 1234",
        "phone": PHONE,
        "bank_name": "กสิกรไทย",
        "account_number": ACCOUNT,
        "referral": "",
        "consent": "on",
    }
    data.update(overrides)
    return data


def logged():
    """Log rows written by customer actions (logging in also writes a row)."""
    return ActivityLog.objects.exclude(action=ActivityLog.Action.LOGIN)


def message_texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.fixture
def customer(make_customer):
    return make_customer(name="เดิม", phone="0800000001")


def admin_urls(customer) -> list[tuple[str, str]]:
    """Every admin-only URL with the method it accepts."""
    return [
        ("get", CREATE),
        ("post", CREATE),
        ("get", reverse("customer_edit", args=[customer.pk])),
        ("post", reverse("customer_edit", args=[customer.pk])),
        ("get", reverse("customer_delete", args=[customer.pk])),
        ("post", reverse("customer_delete", args=[customer.pk])),
        ("post", HIDE),
    ]


# --- Permission matrix ----------------------------------------------------


def test_staff_get_403_on_every_admin_url_and_nothing_changes(
    client, staff, customer
) -> None:
    client.force_login(staff)

    for method, url in admin_urls(customer):
        response = getattr(client, method)(
            url, {"ids": str(customer.pk), "hidden": "1"}
        )
        assert response.status_code == 403, (method, url)

    customer.refresh_from_db()
    assert customer.is_hidden is False
    assert Customer.objects.count() == 1
    assert logged().count() == 0


def test_anonymous_users_are_sent_to_login_from_every_admin_url(
    client, customer
) -> None:
    for method, url in admin_urls(customer):
        response = getattr(client, method)(url)
        assert response.status_code == 302, (method, url)
        assert response.url.startswith(reverse("login")), (method, url)

    assert Customer.objects.count() == 1


def test_staff_page_has_no_admin_controls(client, staff, customer) -> None:
    client.force_login(staff)

    page = client.get(LIST).text

    for forbidden in (CREATE, HIDE, "/edit/", "/delete/", "เพิ่มลูกค้า"):
        assert forbidden not in page


def test_admin_page_has_the_controls(client, admin, customer) -> None:
    client.force_login(admin)

    page = client.get(LIST).text

    for expected in (CREATE, HIDE, f"/customers/{customer.pk}/edit/", "เพิ่มลูกค้า"):
        assert expected in page


# --- Add ------------------------------------------------------------------


def test_admin_adds_a_customer(client, admin) -> None:
    client.force_login(admin)

    response = client.post(CREATE, form_data(phone="081-111 2222"))

    assert response.status_code == 302
    created = Customer.objects.get()
    assert created.created_by == Customer.CreatedBy.ADMIN
    assert created.phone == PHONE
    assert created.referral == "บริษัท"
    assert created.consent_at is not None


def test_add_uses_the_same_validation_as_the_public_form(client, admin) -> None:
    client.force_login(admin)

    response = client.post(CREATE, form_data(phone="-", account_number="abc"))

    assert response.status_code == 200
    assert {"phone", "account_number"} <= set(response.context["form"].errors)
    assert Customer.objects.count() == 0
    assert logged().count() == 0


def test_add_form_asks_for_consent_but_has_no_honeypot(client, admin) -> None:
    client.force_login(admin)

    fields = client.get(CREATE).context["form"].fields

    assert "consent" in fields
    assert "website" not in fields


def test_add_without_consent_is_refused(client, admin) -> None:
    client.force_login(admin)

    response = client.post(CREATE, form_data(consent=""))

    assert response.status_code == 200
    assert "consent" in response.context["form"].errors
    assert Customer.objects.count() == 0


def test_edit_asks_for_consent_only_when_none_is_recorded(
    client, admin, make_customer
) -> None:
    client.force_login(admin)
    without = make_customer(consent_at=None)
    with_consent = make_customer(consent_at=timezone.now())

    def form_fields(customer):
        url = reverse("customer_edit", args=[customer.pk])
        return client.get(url).context["form"].fields

    assert "consent" in form_fields(without)
    assert "consent" not in form_fields(with_consent)


def test_edit_keeps_the_original_consent_time(client, admin, make_customer) -> None:
    client.force_login(admin)
    first = timezone.now() - timedelta(days=30)
    customer = make_customer(consent_at=first)

    client.post(reverse("customer_edit", args=[customer.pk]), form_data(consent=""))

    customer.refresh_from_db()
    assert customer.consent_at == first
    assert customer.name == "สมชาย ใจดี"


def test_phone_is_free_text_but_a_plain_number_is_cleaned(client, admin) -> None:
    client.force_login(admin)

    client.post(CREATE, form_data(name="ก", phone="ใช้เบอร์ John"))
    client.post(CREATE, form_data(name="ข", phone="081-111 2222"))

    assert Customer.objects.get(name="ก").phone == "ใช้เบอร์ John"
    assert Customer.objects.get(name="ข").phone == PHONE


def test_a_note_is_accepted_but_a_lone_dash_is_not(client, admin) -> None:
    client.force_login(admin)

    refused = client.post(CREATE, form_data(license_plate="-", bank_name="ยังไม่มี"))

    assert "license_plate" in refused.context["form"].errors
    assert "bank_name" not in refused.context["form"].errors
    assert Customer.objects.count() == 0


# --- Duplicate phone: allowed, but flagged --------------------------------


def test_duplicate_phone_is_saved_with_a_warning(client, admin, make_customer) -> None:
    make_customer(name="คนแรก เดิม", phone=PHONE)
    client.force_login(admin)

    response = client.post(CREATE, form_data())

    assert Customer.objects.filter(phone=PHONE).count() == 2
    warnings = [text for text in message_texts(response) if "ซ้ำ" in text]
    assert len(warnings) == 1
    assert "คนแรก เดิม" in warnings[0]
    assert PHONE not in warnings[0]


def test_unique_phone_gives_no_warning(client, admin, customer) -> None:
    client.force_login(admin)

    response = client.post(CREATE, form_data())

    assert not [text for text in message_texts(response) if "ซ้ำ" in text]


def test_list_flags_duplicate_phones_for_admin_only(
    client, admin, staff, make_customer
) -> None:
    make_customer(phone=PHONE)
    make_customer(phone=PHONE)
    make_customer(phone="0800000009")

    client.force_login(admin)
    admin_page = client.get(LIST)
    client.force_login(staff)
    staff_page = client.get(LIST)

    assert admin_page.text.count("เบอร์ซ้ำ</span>") == 4  # 2 rows, table + cards
    assert "เบอร์ซ้ำ" not in staff_page.text
    assert not hasattr(staff_page.context["page"].object_list[0], "has_duplicate_phone")


def test_edit_page_names_the_other_customers_with_the_same_phone(
    client, admin, make_customer
) -> None:
    make_customer(name="คนแรก", phone=PHONE)
    second = make_customer(name="คนสอง", phone=PHONE)
    client.force_login(admin)

    page = client.get(reverse("customer_edit", args=[second.pk])).text

    assert "เบอร์โทรนี้ซ้ำกับลูกค้ารายอื่น" in page
    assert "คนแรก" in page


def test_public_form_never_reveals_a_duplicate(client, make_customer) -> None:
    make_customer(phone=PHONE)

    response = client.post(
        reverse("register"), form_data(consent="on", website=""), follow=True
    )

    assert Customer.objects.filter(phone=PHONE).count() == 2
    assert "ซ้ำ" not in response.text


# --- Edit -----------------------------------------------------------------


def test_admin_edits_a_customer(client, admin, customer) -> None:
    client.force_login(admin)

    client.post(reverse("customer_edit", args=[customer.pk]), form_data(name="ใหม่"))

    customer.refresh_from_db()
    assert customer.name == "ใหม่"
    assert customer.created_by == Customer.CreatedBy.ADMIN  # origin is not changed


def test_edit_keeps_the_original_source(client, admin, make_customer) -> None:
    from_qr = make_customer(created_by=Customer.CreatedBy.QR_CODE)
    client.force_login(admin)

    client.post(reverse("customer_edit", args=[from_qr.pk]), form_data())

    from_qr.refresh_from_db()
    assert from_qr.created_by == Customer.CreatedBy.QR_CODE


def test_edit_unknown_customer_is_404(client, admin) -> None:
    client.force_login(admin)

    assert client.get(reverse("customer_edit", args=[999999])).status_code == 404


# --- Delete ---------------------------------------------------------------


def test_delete_needs_a_post(client, admin, customer) -> None:
    client.force_login(admin)

    response = client.get(reverse("customer_delete", args=[customer.pk]))

    assert response.status_code == 200
    assert "ลบถาวร" in response.text
    assert Customer.objects.filter(pk=customer.pk).exists()
    assert logged().count() == 0


def test_admin_deletes_a_customer(client, admin, customer) -> None:
    client.force_login(admin)

    response = client.post(reverse("customer_delete", args=[customer.pk]))

    assert response.status_code == 302
    assert not Customer.objects.filter(pk=customer.pk).exists()


# --- Hide / unhide --------------------------------------------------------


def test_hide_must_be_a_post(client, admin, customer) -> None:
    client.force_login(admin)

    assert client.get(HIDE, {"ids": str(customer.pk), "hidden": "1"}).status_code == 405
    customer.refresh_from_db()
    assert customer.is_hidden is False


def test_hidden_customer_disappears_for_staff_at_once(
    client, admin, staff, customer
) -> None:
    client.force_login(admin)
    client.post(HIDE, {"ids": str(customer.pk), "hidden": "1"})

    client.force_login(staff)
    assert "เดิม" not in client.get(LIST).text

    client.force_login(admin)
    client.post(HIDE, {"ids": str(customer.pk), "hidden": "0"})

    client.force_login(staff)
    assert "เดิม" in client.get(LIST).text


def test_bulk_hide_ignores_unknown_and_rubbish_ids(
    client, admin, make_customer
) -> None:
    a, b = make_customer(name="a"), make_customer(name="b")
    untouched = make_customer(name="c")
    client.force_login(admin)

    client.post(HIDE, {"ids": f"{a.pk},{b.pk},999999,abc,-5", "hidden": "1"})

    assert Customer.objects.filter(is_hidden=True).count() == 2
    untouched.refresh_from_db()
    assert untouched.is_hidden is False
    entry = logged().get()
    assert entry.details["customer_ids"] == [a.pk, b.pk]
    assert entry.details["count"] == 2


def test_hiding_what_is_already_hidden_changes_and_logs_nothing(
    client, admin, make_customer
) -> None:
    hidden = make_customer(is_hidden=True)
    client.force_login(admin)

    client.post(HIDE, {"ids": str(hidden.pk), "hidden": "1"})

    assert logged().count() == 0


# --- Activity log ---------------------------------------------------------


def test_each_action_writes_exactly_one_safe_log_row(client, admin, customer) -> None:
    client.force_login(admin)
    edit = reverse("customer_edit", args=[customer.pk])
    delete = reverse("customer_delete", args=[customer.pk])

    steps = [
        ("customer_create", lambda: client.post(CREATE, form_data())),
        ("customer_edit", lambda: client.post(edit, form_data(name="ใหม่"))),
        (
            "customer_hide",
            lambda: client.post(HIDE, {"ids": customer.pk, "hidden": "1"}),
        ),
        (
            "customer_unhide",
            lambda: client.post(HIDE, {"ids": customer.pk, "hidden": "0"}),
        ),
        ("customer_delete", lambda: client.post(delete)),
    ]
    for count, (action, run) in enumerate(steps, start=1):
        run()
        assert logged().count() == count, action
        entry = logged().latest("id")
        assert entry.action == action
        assert entry.user == admin
        assert entry.details["count"] == 1
        assert entry.details["customer_names"]
        assert set(entry.details) == {"customer_ids", "customer_names", "count"}
        for secret in (PHONE, ACCOUNT, "0800000001", "0001234567"):
            assert secret not in str(entry.details)

    # The name is kept in the log after the customer is gone.
    assert logged().latest("id").details["customer_names"] == ["ใหม่"]


# --- Return address -------------------------------------------------------


def test_actions_return_to_the_list_the_admin_came_from(
    client, admin, customer
) -> None:
    client.force_login(admin)
    came_from = f"{LIST}?q=abc&page=2"

    response = client.post(
        HIDE, {"ids": str(customer.pk), "hidden": "1", "next": came_from}
    )

    assert response.url == came_from


@pytest.mark.parametrize(
    "evil", ["https://evil.example/", "//evil.example", "javascript:alert(1)"]
)
def test_return_address_must_be_on_this_site(client, admin, customer, evil) -> None:
    client.force_login(admin)

    response = client.post(HIDE, {"ids": str(customer.pk), "hidden": "1", "next": evil})
    page = client.get(reverse("customer_edit", args=[customer.pk]), {"next": evil}).text

    assert response.url == LIST
    assert evil not in page
