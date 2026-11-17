from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    BaseUserCreationForm,
    PasswordChangeForm,
    SetPasswordForm,
)
from django.core.validators import RegexValidator

# English letters, digits and . _ - only (decided 2026-11-17): easy to type on
# any keyboard and safe in URLs and logs.
USERNAME_RULE = RegexValidator(
    r"^[A-Za-z0-9._-]+\Z",
    "ชื่อผู้ใช้ใช้ได้เฉพาะตัวอักษรภาษาอังกฤษ ตัวเลข และเครื่องหมาย . _ - เท่านั้น",
)
USERNAME_HELP = "ภาษาอังกฤษ ตัวเลข และ . _ - เท่านั้น ไม่เกิน 150 ตัวอักษร"
USERNAME_TAKEN = "มีชื่อผู้ใช้นี้อยู่แล้ว (ไม่สนใจตัวพิมพ์เล็กหรือใหญ่)"
PASSWORD_MISMATCH = "รหัสผ่านทั้งสองช่องไม่ตรงกัน"
PASSWORD_AGAIN_HELP = "พิมพ์รหัสผ่านเดิมอีกครั้งเพื่อยืนยัน"


def username_taken(username: str, exclude_pk: int | None = None) -> bool:
    """True when another account already uses this name, ignoring case
    ("Nisa" and "nisa" would be too easy to mix up)."""
    others = get_user_model().objects.filter(username__iexact=username)
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    return others.exists()


class ThaiPasswordTextsMixin:
    """Thai texts for Django's password forms (its Thai translation is missing
    these). Rules and hashing stay Django's own."""

    password_fields: tuple[str, str] = ("new_password1", "new_password2")

    def _use_thai_password_texts(self) -> None:
        self.error_messages = {
            **self.error_messages,
            "password_mismatch": PASSWORD_MISMATCH,
        }
        first, second = self.password_fields
        self.fields[
            first
        ].help_text = password_validation.password_validators_help_text_html()
        self.fields[second].help_text = PASSWORD_AGAIN_HELP


class UsernameFieldMixin:
    """English-only usernames, unique without regard to case."""

    def _use_username_rules(self) -> None:
        field = self.fields["username"]
        field.validators.append(USERNAME_RULE)
        field.help_text = USERNAME_HELP
        field.error_messages["unique"] = USERNAME_TAKEN

    def clean_username(self) -> str:
        username = self.cleaned_data["username"]
        if username_taken(username, exclude_pk=self.instance.pk):
            raise forms.ValidationError(USERNAME_TAKEN)
        return username


class StaffCreateForm(ThaiPasswordTextsMixin, UsernameFieldMixin, BaseUserCreationForm):
    """Add Staff: username, name and a password typed twice by the admin.

    Django's own form does the password checks and hashing. The account is
    always staff (`is_admin=False`); admins are only made with `create_admin`.
    """

    password_fields = ("password1", "password2")

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name")
        labels = {"first_name": "ชื่อ", "last_name": "นามสกุล"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._use_thai_password_texts()
        self._use_username_rules()
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        for field in self.fields.values():
            field.widget.attrs["autocomplete"] = "off"
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs["autocomplete"] = "new-password"

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        user.is_admin = False
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class StaffEditForm(UsernameFieldMixin, forms.ModelForm):
    """Edit an account's username and name. Role, status and password have
    their own buttons; this form never touches them."""

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name")
        labels = {"first_name": "ชื่อ", "last_name": "นามสกุล"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._use_username_rules()
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        for field in self.fields.values():
            field.widget.attrs["autocomplete"] = "off"


class ThaiSetPasswordForm(ThaiPasswordTextsMixin, SetPasswordForm):
    """An admin sets a new password for someone else."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._use_thai_password_texts()


class ThaiPasswordChangeForm(ThaiPasswordTextsMixin, PasswordChangeForm):
    """Change your own password: asks for the current one first."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._use_thai_password_texts()
        self.error_messages["password_incorrect"] = "รหัสผ่านปัจจุบันไม่ถูกต้อง กรุณาลองอีกครั้ง"
        self.fields["old_password"].label = "รหัสผ่านปัจจุบัน"
        self.fields["new_password2"].label = "ยืนยันรหัสผ่านใหม่"
