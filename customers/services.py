"""Admin actions on customers. Each one changes data and writes one log row.

Views call these; the permission check (`@admin_required`) stays in the view.
The action and its log row share one transaction, so neither exists alone.
"""

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from audit.models import ActivityLog
from audit.services import log_action
from customers.forms import CustomerForm
from customers.models import Customer
from customers.queries import visible_customers

Action = ActivityLog.Action


def _details(customers: list[Customer]) -> dict:
    """Log details: IDs and names only. Never phone or account numbers."""
    return {
        "customer_ids": [customer.pk for customer in customers],
        "customer_names": [customer.full_name for customer in customers],
        "count": len(customers),
    }


@transaction.atomic
def create_customer(
    form: CustomerForm, user: AbstractBaseUser, ip_address: str | None
) -> Customer:
    customer = form.save(commit=False)
    customer.created_by = Customer.CreatedBy.ADMIN
    customer.save()
    log_action(
        Action.CUSTOMER_CREATE,
        user=user,
        details=_details([customer]),
        ip_address=ip_address,
    )
    return customer


@transaction.atomic
def update_customer(
    form: CustomerForm, user: AbstractBaseUser, ip_address: str | None
) -> Customer:
    customer = form.save()
    log_action(
        Action.CUSTOMER_EDIT,
        user=user,
        details=_details([customer]),
        ip_address=ip_address,
    )
    return customer


@transaction.atomic
def delete_customer(
    customer: Customer, user: AbstractBaseUser, ip_address: str | None
) -> None:
    # Copy the name first: after the delete the row is gone.
    details = _details([customer])
    customer.delete()
    log_action(
        Action.CUSTOMER_DELETE, user=user, details=details, ip_address=ip_address
    )


@transaction.atomic
def set_hidden(
    user: AbstractBaseUser, ids: list[int], hidden: bool, ip_address: str | None
) -> int:
    """Hide or unhide customers. Returns how many actually changed.

    IDs come from the browser, so they are re-checked through
    `visible_customers(user)`. Unknown IDs and rows already in the wanted state
    are skipped, and nothing is logged when nothing changed.
    """
    to_change = list(
        visible_customers(user).filter(pk__in=ids, is_hidden=not hidden).order_by("pk")
    )
    if not to_change:
        return 0
    visible_customers(user).filter(
        pk__in=[customer.pk for customer in to_change]
    ).update(is_hidden=hidden, updated_at=timezone.now())
    log_action(
        Action.CUSTOMER_HIDE if hidden else Action.CUSTOMER_UNHIDE,
        user=user,
        details=_details(to_change),
        ip_address=ip_address,
    )
    return len(to_change)
