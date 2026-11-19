import re

from django.core.validators import RegexValidator
from django.db import models

DEFAULT_REFERRAL = "บริษัท"
# Stored for a value the old Excel file did not have. App forms never accept it,
# so only imported rows can hold it.
MISSING = "-"
account_number_text = RegexValidator(r"^(\d+|-)$", "กรุณากรอกเฉพาะตัวเลข")


def normalize_referral(value: str | None) -> str:
    """Trim, collapse repeated spaces, and fall back to the default when blank."""
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned or DEFAULT_REFERRAL


class Customer(models.Model):
    class CreatedBy(models.TextChoices):
        QR_CODE = "qr_code", "QR code"
        ADMIN = "admin", "Admin"
        EXCEL = "excel", "Excel"

    # One name field (the client's data has one name column). Duplicates allowed.
    name = models.CharField(max_length=200)
    license_plate = models.CharField(max_length=50)
    # Free text: a number keeps its leading 0, and old rows hold notes such as
    # "ใช้เบอร์ John".
    phone = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100)
    # Text, not a number: leading zeros matter. Digits only, or MISSING.
    account_number = models.CharField(max_length=30, validators=[account_number_text])
    referral = models.CharField(max_length=150, blank=True, default=DEFAULT_REFERRAL)
    is_hidden = models.BooleanField(default=False)
    created_by = models.CharField(max_length=10, choices=CreatedBy.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        # Name only: never put phone or account numbers in a string that may be logged.
        return self.name

    def save(self, *args, **kwargs) -> None:
        self.referral = normalize_referral(self.referral)
        super().save(*args, **kwargs)


class RegistrationAttempt(models.Model):
    """One row per saved public registration, used only for rate limiting.

    Holds no customer data. Old rows are deleted by `customers/rate_limit.py`.
    """

    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["ip_address", "created_at"])]

    def __str__(self) -> str:
        return f"{self.ip_address} {self.created_at:%Y-%m-%d %H:%M}"
