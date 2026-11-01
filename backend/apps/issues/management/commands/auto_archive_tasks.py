"""Archive the tasks that have been completed (a done stage, or the board's last column) for 7 days. Run daily by
cron on the server:

    15 2 * * * root /usr/local/bin/trackflow-manage auto_archive_tasks
"""
from django.core.management.base import BaseCommand

from apps.issues.archive import auto_archive


class Command(BaseCommand):
    help = "Archive tasks that have been completed for 7 days."

    def handle(self, *args, **options):
        self.stdout.write(f"Archived {auto_archive()} task(s).")
