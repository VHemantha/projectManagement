"""Make an account the CEO (the primary super admin): full access to the application and the only
person who may control the coordination agent. Run on the server; not possible through the API.

    python manage.py set_ceo dushan@afitconnect.com
"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.coordinator.services import audit


class Command(BaseCommand):
    help = "Make the account with this email the CEO (full access; controls the coordination agent)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email__iexact=email.strip(), is_agent=False).first()
        if user is None:
            raise CommandError(f"No account with the email {email}.")
        for other in User.objects.filter(role=User.Role.CEO).exclude(pk=user.pk):
            other.role = User.Role.MEMBER  # one CEO; the previous one keeps their admin rights
            other.save(update_fields=["role"])
            self.stdout.write(f"{other.email} is no longer the CEO (still an admin).")
        user.role = User.Role.CEO
        user.save()
        audit(None, "set CEO", user.email, via="manage.py set_ceo")
        self.stdout.write(self.style.SUCCESS(f"{user.display_name} <{user.email}> is now the CEO."))
