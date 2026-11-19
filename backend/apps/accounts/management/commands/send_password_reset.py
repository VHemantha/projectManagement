"""Email someone a link to set a new password (AFIT, 18 Nov 2026).

    sudo trackflow-manage send_password_reset sandani.t@afitconnect.com

For an account that exists already (an invitation can't be resent to it). The link works once and
expires after PASSWORD_RESET_TIMEOUT."""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.password_reset import can_reset, send_reset_email


class Command(BaseCommand):
    help = "Email a user a single-use link to set a new password."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No account has the email {email}. Invite them from the People page instead.")
        if not can_reset(user):
            raise CommandError(f"{user.email}'s account is inactive (or is the agent): reactivate it first.")
        if not send_reset_email(user):
            raise CommandError(f"The email to {user.email} couldn't be sent - check the mail settings and the log.")
        self.stdout.write(self.style.SUCCESS(f"Password reset link sent to {user.email}."))
