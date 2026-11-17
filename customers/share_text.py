"""Plain text for Copy and Share. One labelled block per customer."""

from collections.abc import Iterable

from customers.models import Customer
from customers.visibility import export_values


def build_share_text(customers: Iterable[Customer]) -> str:
    """Example:

    ชื่อ: สมชาย ใจดี
    ทะเบียนรถ: 1กข 1234
    ธนาคาร: กสิกรไทย
    เลขที่บัญชี: 1234567890

    Blocks are separated by one blank line. Fields come from `export_values`.
    """
    blocks = [
        "\n".join(f"{label}: {value}" for label, value in export_values(customer))
        for customer in customers
    ]
    return "\n\n".join(blocks)
