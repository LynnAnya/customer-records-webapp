from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet
from django.db.models.functions import Collate

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
    user: AbstractBaseUser | AnonymousUser, query: str = "", sort: str | None = None
) -> QuerySet[Customer]:
    """Customers this user may see, filtered by the search text and sorted.

    Every word must match at least one field the user may see. Phone is only in
    that list for admins, so a staff search can never match on phone.
    """
    customers = visible_customers(user)
    fields = visible_fields(user)
    for word in query.split():
        matches_word = Q()
        for field in fields:
            matches_word |= Q(**{f"{field}__icontains": word})
        customers = customers.filter(matches_word)
    return customers.order_by(*SORTS[clean_sort(sort)])
