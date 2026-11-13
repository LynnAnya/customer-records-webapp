from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Login account for admins and staff.

    `is_admin` is the only admin flag. `is_staff` and `is_superuser` come from
    AbstractUser, stay False and are never used for permissions.
    """

    is_admin = models.BooleanField(default=False)
