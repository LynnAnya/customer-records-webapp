from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.functions import Collate

from customers.filters import CustomerFilters, apply_filters
from customers.models import NO_DATA_PATTERN, Customer, is_no_data
from customers.visibility import can_see_phone, visible_fields

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
    "name_az": (_thai("name").asc(), "id"),
    "name_za": (_thai("name").desc(), "-id"),
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
    customers = _flag_duplicates(customers, user)
    return customers.order_by(*SORTS[clean_sort(sort)])


def pinned_customers(
    user: AbstractBaseUser | AnonymousUser, ids: list[int]
) -> tuple[list[Customer], list[int]]:
    """Ticked customers in tick order, plus the IDs this user may not see.

    IDs from the browser are never trusted: each one is looked up through
    `visible_customers(user)`, so hidden or deleted customers are dropped.
    """
    by_id = _flag_duplicates(visible_customers(user), user).in_bulk(ids)
    pinned = [by_id[pk] for pk in ids if pk in by_id]
    dropped = [pk for pk in ids if pk not in by_id]
    return pinned, dropped


def _flag_duplicates(
    customers: QuerySet[Customer], user: AbstractBaseUser | AnonymousUser
) -> QuerySet[Customer]:
    """Add `has_duplicate_phone` and `has_duplicate_account`, for admins only.

    Staff never see phones, so they get no hint about them either; the account
    tag is admin only too (decided by the user, 2026-11-24). Any other customer
    counts, also the same person with another car.
    """
    if not can_see_phone(user):
        return customers
    # "-" and 0 mean "not known yet", so they never count as a duplicate.
    same_account = (
        Customer.objects.filter(account_number=OuterRef("account_number"))
        .exclude(account_number__regex=NO_DATA_PATTERN)
        .exclude(pk=OuterRef("pk"))
    )
    customers = customers.annotate(has_duplicate_account=Exists(same_account))
    same_phone = (
        Customer.objects.filter(phone=OuterRef("phone"))
        .exclude(phone__regex=NO_DATA_PATTERN)
        .exclude(pk=OuterRef("pk"))
    )
    return customers.annotate(has_duplicate_phone=Exists(same_phone))


def account_duplicates(customer: Customer) -> QuerySet[Customer]:
    """Other customers with the same account number. For admin pages only."""
    if is_no_data(customer.account_number):
        return Customer.objects.none()
    return Customer.objects.filter(account_number=customer.account_number).exclude(
        pk=customer.pk
    )


def phone_duplicates(customer: Customer) -> QuerySet[Customer]:
    """Other customers with the same phone. For admin pages only."""
    if is_no_data(customer.phone):
        return Customer.objects.none()
    return Customer.objects.filter(phone=customer.phone).exclude(pk=customer.pk)
