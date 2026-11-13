from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet
from django.db.models.functions import Collate

from customers.filters import CustomerFilters, apply_filters
from customers.models import Customer
from customers.visibility import visible_fields

# Postgres' built-in Thai (ICU) collation, so names sort ก-ฮ the way Thai readers
# expect (the database default would put เ แ โ ใ ไ after ฮ).
THAI_COLLATION = "th-x-icu"

DEFAULT_SORT = "newest"


def _thai(field: str) -> Collate:
    return Collate(field, THAI_COLLATION)


# Sort keys the browser may send. Anything else falls back to DEFAULT_SORT, so a
# raw field name from the URL never reaches the database.
SORTS = {
    "newest": ("-created_at", "-id"),
    "oldest": ("created_at", "id"),
    "name_az": (_thai("first_name").asc(), _thai("last_name").asc(), "id"),
    "name_za": (_thai("first_name").desc(), _thai("last_name").desc(), "-id"),
    "bank_az": (_thai("bank_name").asc(), "id"),
    "bank_za": (_thai("bank_name").desc(), "-id"),
}


def visible_customers(user: AbstractBaseUser | AnonymousUser) -> QuerySet[Customer]:
    """The only way views read customers.

    Admins get every customer. Staff get non-hidden customers only.
    Anyone else (anonymous, deactivated) gets nothing.
    """
    if not user.is_authenticated or not user.is_active:
        return Customer.objects.none()
    if user.is_admin:
        return Customer.objects.all()
    return Customer.objects.filter(is_hidden=False)


def clean_sort(sort: str | None) -> str:
    return sort if sort in SORTS else DEFAULT_SORT


def search_customers(
    user: AbstractBaseUser | AnonymousUser,
    query: str = "",
    sort: str | None = None,
    filters: CustomerFilters | None = None,
) -> QuerySet[Customer]:
    """Customers this user may see, filtered by search text and filters, sorted.

    Every word must match at least one field the user may see. Phone is only in
    that list for admins, so a staff search can never match on phone.
    """
    customers = visible_customers(user)
    if filters:
        customers = apply_filters(customers, filters)
    fields = visible_fields(user)
    for word in query.split():
        matches_word = Q()
        for field in fields:
            matches_word |= Q(**{f"{field}__icontains": word})
        customers = customers.filter(matches_word)
    return customers.order_by(*SORTS[clean_sort(sort)])


def pinned_customers(
    user: AbstractBaseUser | AnonymousUser, ids: list[int]
) -> tuple[list[Customer], list[int]]:
    """Ticked customers in tick order, plus the IDs this user may not see.

    IDs from the browser are never trusted: each one is looked up through
    `visible_customers(user)`, so hidden or deleted customers are dropped.
    """
    by_id = visible_customers(user).in_bulk(ids)
    pinned = [by_id[pk] for pk in ids if pk in by_id]
    dropped = [pk for pk in ids if pk not in by_id]
    return pinned, dropped
