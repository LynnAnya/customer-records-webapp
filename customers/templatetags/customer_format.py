from django import template

from customers.visibility import mask_account_number

register = template.Library()


@register.filter
def masked(account_number: str) -> str:
    return mask_account_number(account_number)
