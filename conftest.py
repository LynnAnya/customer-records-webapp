"""Shared test fixtures. All data here is fake."""

from collections.abc import Callable

import pytest
from django.contrib.auth import get_user_model

from customers.models import Customer


@pytest.fixture
def admin(db):
    return get_user_model().objects.create_user(
        username="admin1", password="x", first_name="สมชาย", is_admin=True
    )


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        username="staff1", password="x", first_name="นิสา"
    )


@pytest.fixture
def make_customer(db) -> Callable[..., Customer]:
    def _make(**overrides) -> Customer:
        fields = {
            "first_name": "ทดสอบ",
            "last_name": "ตัวอย่าง",
            "license_plate": "1กข 1234",
            "phone": "0800000000",
            "bank_name": "ธนาคารทดสอบ",
            "account_number": "0001234567",
            "created_by": Customer.CreatedBy.ADMIN,
        }
        fields.update(overrides)
        return Customer.objects.create(**fields)

    return _make
