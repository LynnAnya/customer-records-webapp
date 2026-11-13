import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Create an admin account. The password is typed at a hidden prompt."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        username = options["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"Username '{username}' already exists.")

        first_name = input("First name: ").strip()
        last_name = input("Last name: ").strip()
        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_admin=True,
            is_staff=False,
            is_superuser=False,
        )

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("The two passwords do not match.")
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin '{username}' created."))
