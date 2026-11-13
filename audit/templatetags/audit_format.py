from datetime import datetime

from django import template

from audit import labels

register = template.Library()


@register.filter
def action_label(action: str) -> str:
    return labels.action_label(action)


@register.filter
def is_alert(action: str) -> bool:
    return action in labels.ALERT_ACTIONS


@register.filter
def describe(details: dict) -> str:
    return labels.describe_details(details)


@register.filter
def ago(moment: datetime) -> str:
    return labels.time_ago(moment)
