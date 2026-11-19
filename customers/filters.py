"""Filters and selected IDs for the customers page, read safely from the URL."""

import re
from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet
from django.db.models.functions import Collate
from django.http import QueryDict
from django.utils.dateparse import parse_date

from customers.models import Customer

MAX_SELECTED = 1000
HIDDEN_CHOICES = ("visible", "hidden")
MAX_TEXT = 100  # longest text accepted in a filter box
# Thai vowels written before the consonant they belong to. Thai dictionary
# order (our `th-x-icu` sort) skips them, so "เนเน่" sorts under น.
LEADING_VOWELS = "เแโใไ"


@dataclass(frozen=True)
class CustomerFilters:
    name: str = ""  # name starts with, by first consonant (see name_starts_with)
    plate: str = ""  # license plate contains
    bank: str = ""  # exact bank, any case (from the dropdown)
    source: str = ""  # a Customer.CreatedBy value
    referral: str = ""
    date_from: date | None = None
    date_to: date | None = None
    hidden: str = ""  # "visible" | "hidden"; admins only

    def as_params(self) -> dict[str, str]:
        """Only the filters that are set, as URL parameters."""
        params = {
            "name": self.name,
            "plate": self.plate,
            "bank": self.bank,
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
        name=params.get("name", "").strip()[:MAX_TEXT],
        plate=params.get("plate", "").strip()[:MAX_TEXT],
        bank=params.get("bank", "").strip()[:MAX_TEXT],
        # Where a customer came from is an admin filter; staff do not get it.
        source=source if is_admin and source in Customer.CreatedBy.values else "",
        referral=params.get("referral", "").strip()[:MAX_TEXT],
        date_from=_safe_date(params.get("from")),
        date_to=_safe_date(params.get("to")),
        # Staff never see hidden customers, so this filter does not exist for them.
        hidden=hidden if is_admin and hidden in HIDDEN_CHOICES else "",
    )


def apply_filters(
    customers: QuerySet[Customer], filters: CustomerFilters
) -> QuerySet[Customer]:
    if filters.name:
        customers = customers.filter(name_starts_with(filters.name))
    if filters.plate:
        customers = customers.filter(license_plate__icontains=filters.plate)
    if filters.bank:
        customers = customers.filter(bank_name__iexact=filters.bank)
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


def name_starts_with(text: str) -> Q:
    """Names that start with `text` the way Thai dictionary order groups them.

    "น" also finds "เนเน่", "แน่น" and "โน้ต" (a leading vowel is skipped), so
    the filter agrees with the name sort. Text that itself starts with a
    leading vowel ("เน") is matched exactly as typed. Any letter case.
    """
    if text[0] in LEADING_VOWELS:
        return Q(name__istartswith=text)
    after_vowel = f"^[{LEADING_VOWELS}]{re.escape(text)}"
    return Q(name__istartswith=text) | Q(name__iregex=after_vowel)


def referral_choices(customers: QuerySet[Customer]) -> list[str]:
    """Referral values for the filter dropdown, each spelling variant once.

    Pass `visible_customers(user)`, so staff never learn a referral that only
    hidden customers have.
    """
    return _distinct_values(customers, "referral")


def bank_choices(customers: QuerySet[Customer]) -> list[str]:
    """Bank names already saved, for the bank dropdown. Same rules as referral."""
    return _distinct_values(customers, "bank_name")


def _distinct_values(customers: QuerySet[Customer], field: str) -> list[str]:
    """Distinct values of one field in Thai order, each spelling variant once."""
    values = (
        customers.order_by(Collate(field, "th-x-icu"))
        .values_list(field, flat=True)
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
