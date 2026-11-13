from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import QuerySet

from customers.models import Customer


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
