import re

from django.core.validators import RegexValidator
from django.db import models

DEFAULT_REFERRAL = "บริษัท"

digits_only = RegexValidator(r"^\d+$", "กรุณากรอกเฉพาะตัวเลข")


def normalize_referral(value: str | None) -> str:
    """Trim, collapse repeated spaces, and fall back to the default when blank."""
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned or DEFAULT_REFERRAL


class Customer(models.Model):
    class CreatedBy(models.TextChoices):
        QR_CODE = "qr_code", "QR code"
        ADMIN = "admin", "Admin"
        EXCEL = "excel", "Excel"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    license_plate = models.CharField(max_length=50)
    # Text, not numbers: leading zeros matter and we never do maths on them.
    phone = models.CharField(max_length=20, validators=[digits_only])
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=30, validators=[digits_only])
    referral = models.CharField(max_length=150, blank=True, default=DEFAULT_REFERRAL)
    is_hidden = models.BooleanField(default=False)
    created_by = models.CharField(max_length=10, choices=CreatedBy.choices)
    consent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        # Name only: never put phone or account numbers in a string that may be logged.
        return self.full_name

    def save(self, *args, **kwargs) -> None:
        self.referral = normalize_referral(self.referral)
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
