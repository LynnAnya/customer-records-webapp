from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    """Raised when code tries to change or delete an activity log row."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError("Activity log rows cannot be updated.")

    def delete(self):
        raise AppendOnlyError("Activity log rows cannot be deleted.")


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login"
        LOGIN_FAILED = "login_failed"
        CUSTOMER_CREATE = "customer_create"
        CUSTOMER_EDIT = "customer_edit"
        CUSTOMER_DELETE = "customer_delete"
        CUSTOMER_HIDE = "customer_hide"
        CUSTOMER_UNHIDE = "customer_unhide"
        COPY = "copy"
        SHARE = "share"
        PDF_EXPORT = "pdf_export"
        STAFF_CREATED = "staff_created"
        STAFF_PASSWORD_RESET = "staff_password_reset"
        STAFF_DEACTIVATED = "staff_deactivated"
        STAFF_REACTIVATED = "staff_reactivated"
        PASSWORD_CHANGED = "password_changed"
        EXCEL_IMPORT = "excel_import"

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # PROTECT: users are deactivated, never deleted, so history stays attributable.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_logs",
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=30, choices=Action.choices)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username} {self.action}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Activity log rows cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Activity log rows cannot be deleted.")
