from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Login account for admins and staff.

    `is_admin` is the only admin flag. `is_staff` and `is_superuser` come from
    AbstractUser, stay False and are never used for permissions.
    """

    class Theme(models.TextChoices):
        LIGHT = "light", "สว่าง"
        DARK = "dark", "มืด"
        SYSTEM = "system", "ตามอุปกรณ์"

    is_admin = models.BooleanField(default=False)
    # Saved on the account so it follows the person, not the browser: on a
    # shared computer each person keeps their own theme.
    theme = models.CharField(max_length=6, choices=Theme.choices, default=Theme.SYSTEM)
