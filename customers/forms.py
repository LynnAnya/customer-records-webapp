import re

from django import forms
from django.core.validators import RegexValidator

from customers.models import MISSING, Customer

TEXT_INPUT = {"autocomplete": "off"}
NUMBER_INPUT = {"inputmode": "numeric", "autocomplete": "off"}


class DigitsField(forms.CharField):
    """Text field for numbers: removes the spaces and dashes people type."""

    def to_python(self, value: str | None) -> str:
        return re.sub(r"[\s-]", "", super().to_python(value))


def clean_phone_text(value: str) -> str:
    """Phone is free text. A plain number loses its spaces and dashes
    ("081-111 2222" -> "0811112222"); anything else is kept as typed."""
    text = re.sub(r"\s+", " ", value).strip()
    digits = re.sub(r"[\s-]", "", text)
    return digits if digits.isdigit() else text


def is_placeholder(value: str) -> bool:
    """True for "-", "--" and the like: a stand-in, not real data."""
    return bool(value) and not value.replace("-", "").strip()


PLACEHOLDER_ERROR = "กรุณากรอกข้อมูลจริง หรือพิมพ์หมายเหตุ เช่น ยังไม่มี"
REQUIRED_ERROR = "กรุณากรอกข้อมูลในช่องนี้"
CUSTOMER_FIELDS = [
    "name",
    "license_plate",
    "phone",
    "bank_name",
    "account_number",
    "referral",
]


class CustomerForm(forms.ModelForm):
    """Shared customer form: the public QR page and the admin pages both use it.

    Every field except referral is required, and a lone "-" is refused: "-" is
    reserved for values missing from the old Excel file.
    """

    account_number = DigitsField(
        label="เลขที่บัญชี",
        validators=[
            RegexValidator(r"^\d{1,20}$", "กรุณากรอกเลขที่บัญชีเป็นตัวเลข ไม่เกิน 20 หลัก")
        ],
        widget=forms.TextInput(attrs=NUMBER_INPUT),
    )

    class Meta:
        model = Customer
        fields = CUSTOMER_FIELDS
        labels = {
            "name": "ชื่อ",
            "license_plate": "ทะเบียนรถ",
            "phone": "เบอร์โทรศัพท์",
            "bank_name": "ธนาคาร",
            "referral": "ผู้แนะนำ (ถ้ามี)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "license_plate": forms.TextInput(attrs=TEXT_INPUT),
            "phone": forms.TextInput(attrs={**TEXT_INPUT, "inputmode": "tel"}),
            "bank_name": forms.TextInput(attrs=TEXT_INPUT),
            "referral": forms.TextInput(attrs=TEXT_INPUT),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The model default would pre-fill the box; blank is saved as the default.
        self.fields["referral"].initial = ""
        for name in CUSTOMER_FIELDS:
            self.fields[name].error_messages["required"] = REQUIRED_ERROR

    def clean_phone(self) -> str:
        return clean_phone_text(self.cleaned_data["phone"])

    def clean(self) -> dict:
        cleaned = super().clean()
        for name in ("name", "license_plate", "phone", "bank_name"):
            if is_placeholder(cleaned.get(name, "")):
                self.add_error(name, PLACEHOLDER_ERROR)
        return cleaned


class DigitsOrMissingField(DigitsField):
    """Like DigitsField, but a lone "-" (or "--") is kept as "-"."""

    def to_python(self, value: str | None) -> str:
        text = forms.CharField.to_python(self, value)
        return MISSING if is_placeholder(text) else super().to_python(value)


ADMIN_ACCOUNT_ERROR = "กรุณากรอกเลขที่บัญชีเป็นตัวเลข ไม่เกิน 20 หลัก หรือใส่ - ถ้ายังไม่มี"


class AdminCustomerForm(CustomerForm):
    """Admin add and edit: the shared fields, no honeypot.

    Unlike the public QR form, "-" is accepted in every field, for details that
    are not known yet (decided by the user, 2026-11-24). The account number is
    still digits only, or "-".
    """

    account_number = DigitsOrMissingField(
        label="เลขที่บัญชี",
        validators=[RegexValidator(r"^(\d{1,20}|-)$", ADMIN_ACCOUNT_ERROR)],
        widget=forms.TextInput(attrs=NUMBER_INPUT),
    )

    @property
    def customer_fields(self) -> list[forms.BoundField]:
        return [self[name] for name in CUSTOMER_FIELDS]

    def clean(self) -> dict:
        cleaned = forms.ModelForm.clean(self)
        for name in ("name", "license_plate", "phone", "bank_name"):
            if is_placeholder(cleaned.get(name, "")):
                cleaned[name] = MISSING
        return cleaned


class ImportCustomerForm(CustomerForm):
    """One row of the old Excel file. Empty cells are allowed and saved as "-"."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        self.fields["account_number"].validators = [
            RegexValidator(r"^(\d{1,20}|-)$", "กรุณากรอกเลขที่บัญชีเป็นตัวเลข ไม่เกิน 20 หลัก")
        ]

    def clean_account_number(self) -> str:
        return self.cleaned_data["account_number"] or MISSING

    def clean(self) -> dict:
        cleaned = forms.ModelForm.clean(self)
        for name in ("name", "license_plate", "phone", "bank_name"):
            if name in cleaned and (not cleaned[name] or is_placeholder(cleaned[name])):
                cleaned[name] = MISSING
        return cleaned


class PublicRegistrationForm(CustomerForm):
    """The QR form: adds a honeypot that only bots fill in."""

    HONEYPOT_FIELD = "website"

    website = forms.CharField(
        required=False,
        label="เว็บไซต์",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    @property
    def customer_fields(self) -> list[forms.BoundField]:
        """The fields a person fills in, without the honeypot."""
        return [self[name] for name in CUSTOMER_FIELDS]

    def is_bot(self) -> bool:
        return bool(self.cleaned_data.get(self.HONEYPOT_FIELD))


MAX_EXCEL_BYTES = 5 * 1024 * 1024
XLSX_TYPES = ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExcelUploadForm(forms.Form):
    """The admin's Excel upload. The rows themselves are checked by importing.py."""

    file = forms.FileField(
        label="ไฟล์ Excel (.xlsx)",
        error_messages={"required": "กรุณาเลือกไฟล์ Excel", "empty": "ไฟล์นี้ว่างเปล่า"},
        widget=forms.FileInput(attrs={"accept": XLSX_TYPES}),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                "กรุณาเลือกไฟล์ Excel นามสกุล .xlsx (ไฟล์ .xls หรือ .csv ให้เปิดใน Excel "
                "แล้วบันทึกเป็น .xlsx ก่อน)"
            )
        if upload.size > MAX_EXCEL_BYTES:
            raise forms.ValidationError("ไฟล์ใหญ่เกิน 5 MB")
        return upload
