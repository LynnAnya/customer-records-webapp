"""Fill the local database with fake customers. Never real data."""

import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from customers.models import MISSING, Customer

FIRST_NAMES = [
    "สมชาย", "สมหญิง", "นิสา", "วิชัย", "กมล", "ไพโรจน์", "เกศินี", "ธนพล", "ประภา",
    "อรุณ", "แก้วตา", "โสภา", "ใจดี", "ชาตรี", "ขวัญใจ", "ดวงใจ", "ณัฐพล", "ปิยะ",
    "รัตนา", "ศิริพร", "เอกชัย", "มานะ", "ยุพิน", "บุญมี", "John", "Mali",
]  # fmt: skip
LAST_NAMES = [
    "ใจดี", "รักไทย", "ศรีสุข", "ทองดี", "แสงทอง", "บุญมา", "วงศ์ใหญ่", "สุขสบาย",
    "พึ่งธรรม", "เจริญผล", "มั่นคง", "อินทร์แก้ว", "คงเจริญ", "นาคสวัสดิ์", "Smith",
]  # fmt: skip
BANKS = [
    "กสิกรไทย", "ไทยพาณิชย์", "กรุงเทพ", "กรุงไทย", "กรุงศรีอยุธยา", "ออมสิน",
    "ทหารไทยธนชาต", "ธ.ก.ส.",
]  # fmt: skip
REFERRALS = ["", "", "", "คุณสมศรี", "คุณวิทยา", "ร้านเจริญยนต์", "Facebook", "facebook"]
MISSABLE = ["license_plate", "phone", "bank_name", "account_number"]
PLATE_LETTERS = "กขคงจฉชฌญฎธนบผพภมยรลวศษสหฬอฮ"
PROVINCES = ["กรุงเทพมหานคร", "เชียงใหม่", "ขอนแก่น", "ชลบุรี", "นครราชสีมา", "สงขลา"]


def _fake_plate(rng: random.Random) -> str:
    letters = rng.choice(PLATE_LETTERS) + rng.choice(PLATE_LETTERS)
    return (
        f"{rng.randint(1, 9)}{letters} {rng.randint(1, 9999)} {rng.choice(PROVINCES)}"
    )


class Command(BaseCommand):
    help = "Create fake customers for local development (DEBUG only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=60)
        parser.add_argument(
            "--clear", action="store_true", help="Delete all customers first."
        )

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo only runs when DEBUG is on (never in production)."
            )

        if options["clear"]:
            deleted, _ = Customer.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} rows.")

        rng = random.Random(2026)
        now = timezone.now()
        for index in range(options["count"]):
            customer = Customer.objects.create(
                name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                license_plate=_fake_plate(rng),
                # 099-99x-xxxx: an obviously fake block, not real numbers.
                phone=f"09999{rng.randint(0, 99999):05d}",
                bank_name=rng.choice(BANKS),
                account_number=f"{rng.randint(0, 9_999_999_999):010d}",
                referral=rng.choice(REFERRALS),
                is_hidden=rng.random() < 0.1,
                created_by=rng.choice(list(Customer.CreatedBy)),
            )
            if customer.created_by == Customer.CreatedBy.EXCEL and rng.random() < 0.4:
                # Old Excel rows sometimes miss a value; the import saves "-".
                setattr(customer, rng.choice(MISSABLE), MISSING)
                customer.save()
            # Spread the created dates over the last 90 days.
            Customer.objects.filter(pk=customer.pk).update(
                created_at=now - timedelta(days=rng.randint(0, 90), minutes=index)
            )

        self.stdout.write(
            self.style.SUCCESS(f"Created {options['count']} fake customers.")
        )
