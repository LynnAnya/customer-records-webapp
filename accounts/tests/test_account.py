"""Read-only account page. All data is fake."""

from django.urls import reverse

ACCOUNT = reverse("account")


def test_account_page_needs_a_login(client) -> None:
    response = client.get(ACCOUNT)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={ACCOUNT}"


def test_account_page_shows_my_own_details(client, staff) -> None:
    staff.last_name = "ตัวอย่าง"
    staff.save()
    client.force_login(staff)

    page = client.get(ACCOUNT).text

    for text in ("staff1", "นิสา", "ตัวอย่าง", "พนักงาน", "เข้าสู่ระบบล่าสุด", "สร้างบัญชีเมื่อ"):
        assert text in page
    assert "ผู้ดูแลระบบ" not in page


def test_account_page_never_shows_another_user(client, staff, admin) -> None:
    client.force_login(staff)

    page = client.get(ACCOUNT).text

    assert "admin1" not in page
    assert "สมชาย" not in page


def test_admin_sees_the_admin_role(client, admin) -> None:
    client.force_login(admin)

    assert "ผู้ดูแลระบบ" in client.get(ACCOUNT).text


def test_account_page_is_read_only(client, staff) -> None:
    client.force_login(staff)

    assert client.post(ACCOUNT, {"first_name": "x"}).status_code == 405
