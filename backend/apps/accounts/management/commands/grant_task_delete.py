"""Let a named person delete tasks (AFIT, 13 Nov 2026), without making them a team lead or admin.

    manage.py grant_task_delete someone@afitconnect.com
    manage.py grant_task_delete someone@afitconnect.com --revoke
"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Allow (or, with --revoke, stop) a person deleting tasks."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--revoke", action="store_true")

    def handle(self, email, revoke=False, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No account with the email {email}.")
        user.can_delete_tasks = not revoke
        user.save(update_fields=["can_delete_tasks"])
        self.stdout.write(f"{user.display_name} <{user.email}> {'can no longer' if revoke else 'can now'} delete tasks.")
