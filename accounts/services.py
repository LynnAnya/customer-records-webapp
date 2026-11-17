"""Account actions. Each one changes data and writes one log row, together.

Views call these; `@admin_required` stays in the view. Passwords are hashed by
Django's forms and never appear in logs, messages or details.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from accounts.forms import StaffCreateForm, StaffEditForm
from audit.models import ActivityLog
from audit.services import log_action

Action = ActivityLog.Action


class StaffRuleError(Exception):
    """A staff-management rule was broken. The message is safe to show (Thai)."""


def _target(user: AbstractBaseUser) -> dict[str, str]:
    return {"target_username": user.get_username()}


@transaction.atomic
def create_staff(
    form: StaffCreateForm, actor: AbstractBaseUser, ip_address: str | None
) -> AbstractBaseUser:
    user = form.save()
    log_action(
        Action.STAFF_CREATED, user=actor, details=_target(user), ip_address=ip_address
    )
    return user


@transaction.atomic
def edit_staff(
    form: StaffEditForm, actor: AbstractBaseUser, ip_address: str | None
) -> AbstractBaseUser | None:
    """Save a new username or name. Returns None (and logs nothing) when
    nothing changed. A renamed account keeps its history: log rows point to
    the user, and the old username is written in this row's details."""
    if not form.has_changed():
        return None
    previous = form.initial.get("username", "")
    user = form.save()
    details = _target(user)
    if previous and previous != user.get_username():
        details["previous_username"] = previous
    log_action(Action.STAFF_EDITED, user=actor, details=details, ip_address=ip_address)
    return user


@transaction.atomic
def reset_password(
    form: SetPasswordForm, actor: AbstractBaseUser, ip_address: str | None
) -> AbstractBaseUser:
    """An admin sets a new password for someone else.

    Changing the password also ends that person's open sessions (Django ties
    each session to the password hash).
    """
    user = form.save()
    log_action(
        Action.STAFF_PASSWORD_RESET,
        user=actor,
        details=_target(user),
        ip_address=ip_address,
    )
    return user


@transaction.atomic
def change_own_password(
    form: PasswordChangeForm, ip_address: str | None
) -> AbstractBaseUser:
    user = form.save()
    log_action(Action.PASSWORD_CHANGED, user=user, ip_address=ip_address)
    return user


@transaction.atomic
def set_active(
    actor: AbstractBaseUser, target_pk: int, active: bool, ip_address: str | None
) -> AbstractBaseUser:
    """Deactivate or reactivate an account. Accounts are never deleted.

    Rules: nobody deactivates themselves, and the last active admin can never
    be deactivated. Admin rows are locked while we count, so two requests at
    the same moment cannot both pass the check.
    """
    User = get_user_model()
    target = User.objects.select_for_update().get(pk=target_pk)

    if not active:
        if target.pk == actor.pk:
            raise StaffRuleError("ไม่สามารถปิดใช้งานบัญชีของตัวเองได้")
        if target.is_admin:
            other_active_admins = (
                User.objects.select_for_update()
                .filter(is_admin=True, is_active=True)
                .exclude(pk=target.pk)
            )
            if not list(other_active_admins):
                raise StaffRuleError(
                    "ต้องมีผู้ดูแลระบบที่ใช้งานได้อย่างน้อย 1 คน จึงปิดใช้งานบัญชีนี้ไม่ได้"
                )

    if target.is_active == active:
        return target  # nothing to change, nothing to log

    target.is_active = active
    target.save(update_fields=["is_active"])
    log_action(
        Action.STAFF_REACTIVATED if active else Action.STAFF_DEACTIVATED,
        user=actor,
        details=_target(target),
        ip_address=ip_address,
    )
    return target
