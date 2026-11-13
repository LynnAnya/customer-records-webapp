import re

from django import forms
from django.core.validators import RegexValidator

from customers.models import Customer

TEXT_INPUT = {"autocomplete": "off"}
NUMBER_INPUT = {"inputmode": "numeric", "autocomplete": "off"}


class DigitsField(forms.CharField):
    """Text field for numbers: removes the spaces and dashes people type."""

    def to_python(self, value: str | None) -> str:
        return re.sub(r"[\s-]", "", super().to_python(value))


class CustomerForm(forms.ModelForm):
    """Shared customer form: the public QR page and the admin pages both use it."""

    phone = DigitsField(
        label="เบอร์โทรศัพท์",
        validators=[RegexValidator(r"^0\d{9}$", "กรุณากรอกเบอร์โทรศัพท์ 10 หลัก ขึ้นต้นด้วย 0")],
        widget=forms.TextInput(attrs={**NUMBER_INPUT, "inputmode": "tel"}),
    )
    account_number = DigitsField(
        label="เลขที่บัญชี",
        validators=[
            RegexValidator(r"^\d{1,20}$", "กรุณากรอกเลขที่บัญชีเป็นตัวเลข ไม่เกิน 20 หลัก")
        ],
        widget=forms.TextInput(attrs=NUMBER_INPUT),
    )

    class Meta:
        model = Customer
        fields = [
            "first_name",
            "last_name",
            "license_plate",
            "phone",
            "bank_name",
            "account_number",
            "referral",
        ]
        labels = {
            "first_name": "ชื่อ",
            "last_name": "นามสกุล",
            "license_plate": "ทะเบียนรถ",
            "bank_name": "ธนาคาร",
            "referral": "ผู้แนะนำ (ถ้ามี)",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "license_plate": forms.TextInput(attrs=TEXT_INPUT),
            "bank_name": forms.TextInput(attrs=TEXT_INPUT),
            "referral": forms.TextInput(attrs=TEXT_INPUT),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The model default would pre-fill the box; blank is saved as the default.
        self.fields["referral"].initial = ""
        for name in CustomerForm.Meta.fields:
            self.fields[name].error_messages["required"] = "กรุณากรอกข้อมูลในช่องนี้"


class PublicRegistrationForm(CustomerForm):
    """The QR form: adds consent and a honeypot that only bots fill in."""

    HONEYPOT_FIELD = "website"

    consent = forms.BooleanField(
        # Draft wording. The final text is pending a Thai lawyer.
        label="ข้าพเจ้ายินยอมให้บริษัทเก็บและใช้ข้อมูลข้างต้นเพื่อการติดต่อและการโอนเงิน",
        error_messages={"required": "กรุณากดยินยอมก่อนส่งข้อมูล"},
    )
    website = forms.CharField(
        required=False,
        label="เว็บไซต์",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    @property
    def customer_fields(self) -> list[forms.BoundField]:
        """The fields a person fills in, without consent and the honeypot."""
        return [self[name] for name in CustomerForm.Meta.fields]

    def is_bot(self) -> bool:
        return bool(self.cleaned_data.get(self.HONEYPOT_FIELD))
