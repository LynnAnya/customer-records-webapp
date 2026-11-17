"""One `name` field instead of first + last name; phone becomes free text.

Existing rows keep their name: "first last" is copied into `name` before the
two old columns are removed.
"""

import django.core.validators
from django.db import migrations, models


def copy_names(apps, schema_editor) -> None:
    Customer = apps.get_model("customers", "Customer")
    for customer in Customer.objects.only("first_name", "last_name"):
        customer.name = f"{customer.first_name} {customer.last_name}".strip()
        customer.save(update_fields=["name"])


def split_names(apps, schema_editor) -> None:
    Customer = apps.get_model("customers", "Customer")
    for customer in Customer.objects.only("name"):
        first, _, last = customer.name.partition(" ")
        customer.first_name, customer.last_name = first, last
        customer.save(update_fields=["first_name", "last_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0002_registrationattempt"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="name",
            field=models.CharField(default="", max_length=200),
            preserve_default=False,
        ),
        migrations.RunPython(copy_names, split_names),
        migrations.RemoveField(model_name="customer", name="first_name"),
        migrations.RemoveField(model_name="customer", name="last_name"),
        migrations.AlterField(
            model_name="customer",
            name="phone",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="customer",
            name="account_number",
            field=models.CharField(
                max_length=30,
                validators=[
                    django.core.validators.RegexValidator(
                        "^(\\d+|-)$", "กรุณากรอกเฉพาะตัวเลข"
                    )
                ],
            ),
        ),
    ]
