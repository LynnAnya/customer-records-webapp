"""Filters and selected IDs for the customers page, read safely from the URL."""

from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import QuerySet
from django.db.models.functions import Collate
from django.http import QueryDict
from django.utils.dateparse import parse_date

from customers.models import Customer

MAX_SELECTED = 1000
HIDDEN_CHOICES = ("visible", "hidden")


@dataclass(frozen=True)
class CustomerFilters:
    source: str = ""  # a Customer.CreatedBy value
    referral: str = ""
    date_from: date | None = None
    date_to: date | None = None
    hidden: str = ""  # "visible" | "hidden"; admins only

    def as_params(self) -> dict[str, str]:
        """Only the filters that are set, as URL parameters."""
        params = {
            "source": self.source,
            "referral": self.referral,
            "from": self.date_from.isoformat() if self.date_from else "",
            "to": self.date_to.isoformat() if self.date_to else "",
            "hidden": self.hidden,
        }
        return {key: value for key, value in params.items() if value}

    @property
    def active_count(self) -> int:
        return len(self.as_params())


def _safe_date(value: str | None) -> date | None:
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def parse_filters(
    params: QueryDict, user: AbstractBaseUser | AnonymousUser
) -> CustomerFilters:
    """Build filters from the URL. Anything invalid is ignored, never trusted."""
    source = params.get("source", "")
    hidden = params.get("hidden", "")
    is_admin = bool(user.is_authenticated and user.is_admin)
    return CustomerFilters(
        source=source if source in Customer.CreatedBy.values else "",
        referral=params.get("referral", "").strip()[:150],
        date_from=_safe_date(params.get("from")),
        date_to=_safe_date(params.get("to")),
        # Staff never see hidden customers, so this filter does not exist for them.
        hidden=hidden if is_admin and hidden in HIDDEN_CHOICES else "",
    )


def apply_filters(
    customers: QuerySet[Customer], filters: CustomerFilters
) -> QuerySet[Customer]:
    if filters.source:
        customers = customers.filter(created_by=filters.source)
    if filters.referral:
        customers = customers.filter(referral__iexact=filters.referral)
    if filters.date_from:
        customers = customers.filter(created_at__date__gte=filters.date_from)
    if filters.date_to:
        customers = customers.filter(created_at__date__lte=filters.date_to)
    if filters.hidden:
        customers = customers.filter(is_hidden=filters.hidden == "hidden")
    return customers


def referral_choices(customers: QuerySet[Customer]) -> list[str]:
    """Referral values for the filter dropdown, each spelling variant once.

    Pass `visible_customers(user)`, so staff never learn a referral that only
    hidden customers have.
    """
    values = (
        customers.order_by(Collate("referral", "th-x-icu"))
        .values_list("referral", flat=True)
        .distinct()
    )
    seen: set[str] = set()
    choices: list[str] = []
    for value in values:
        if value.casefold() not in seen:
            seen.add(value.casefold())
            choices.append(value)
    return choices


def parse_selected_ids(raw: str | None) -> list[int]:
    """Ticked customer IDs from the browser: digits only, in tick order, no repeats."""
    ids: list[int] = []
    for part in (raw or "").split(","):
        if part.isascii() and part.isdigit() and len(part) <= 12:
            number = int(part)
            if number not in ids:
                ids.append(number)
        if len(ids) >= MAX_SELECTED:
            break
    return ids
