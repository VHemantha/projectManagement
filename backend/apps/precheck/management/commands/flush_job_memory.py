"""Free the AI agent's memory of tasks whose final review was three days ago (AFIT, 20 Nov 2026): their
documents and results leave the agent's knowledge store. Run nightly by cron on the server:

    45 2 * * * root /usr/local/bin/trackflow-manage flush_job_memory
"""
from django.core.management.base import BaseCommand

from apps.precheck.policies import flush_due


class Command(BaseCommand):
    help = "Free the agent's memory of tasks three days after their final review."

    def handle(self, *args, **options):
        out = flush_due()
        self.stdout.write(f"Freed the memory of {out['flushed']} task(s); {out['failed']} could not be reached and will be tried again.")
