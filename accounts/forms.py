from django.contrib.auth import get_user_model
from django.contrib.auth.forms import BaseUserCreationForm


class StaffCreateForm(BaseUserCreationForm):
    """Add Staff: username, name and a password typed twice by the admin.

    Django's own form does the password checks and hashing. The account is
    always staff (`is_admin=False`); admins are only made with `create_admin`.
    """

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name")
        labels = {"first_name": "ชื่อ", "last_name": "นามสกุล"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
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
