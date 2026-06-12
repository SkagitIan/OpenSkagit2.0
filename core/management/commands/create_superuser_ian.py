from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create (or update password for) superuser ian"

    def handle(self, *args, **options):
        User = get_user_model()
        username = "ian"
        email = "ian.larsen.1976@gmail.com"

        password = getpass(f"Password for {username}: ")
        if not password:
            self.stderr.write("Aborted — password cannot be empty.")
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        user.set_password(password)
        if not created:
            user.email = email
            user.is_staff = True
            user.is_superuser = True
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} superuser: {username}"))
