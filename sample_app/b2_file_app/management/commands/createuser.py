from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Creates the test users"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        User.objects.create_user(
            username="super", password="super", email="super@example.com", is_staff=True, is_superuser=True
        )
        User.objects.create_user(username="staff", password="staff", email="staff@example.com", is_staff=True)
        User.objects.create_user(username="user", password="user", email="user@example.com")

        self.stdout.write("Created: ")
        self.stdout.write(" - " + self.style.SUCCESS("super/super"))
        self.stdout.write(" - " + self.style.SUCCESS("staff/staff"))
        self.stdout.write(" - " + self.style.SUCCESS("user/user"))
