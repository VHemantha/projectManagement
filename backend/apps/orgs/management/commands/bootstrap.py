"""Idempotent production bootstrap: the reference data every install needs.

Unlike `seed_demo`, this creates no users, projects or demo content, so it is safe to run on
every deploy (deploy/ec2/server_deploy.sh does). Without it a fresh database has no issue
types and no issue can be created.
"""

from django.core.management.base import BaseCommand

from apps.orgs.models import Organization
from apps.workflow.models import IssueType

from .seed_demo import ISSUE_TYPES


class Command(BaseCommand):
    help = "Create the default organization and system job types if missing (safe to re-run)."

    def handle(self, *args, **options):
        Organization.get_solo()
        created = 0
        for name, icon, color, is_subtask in ISSUE_TYPES:
            _, was_created = IssueType.objects.get_or_create(
                name=name, project=None,
                defaults=dict(icon=icon, color=color, is_subtask=is_subtask),
            )
            created += was_created
        self.stdout.write(f"System job types ready ({created} created).")
