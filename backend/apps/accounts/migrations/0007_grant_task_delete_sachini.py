"""AFIT, 13 Nov 2026: Sachini may delete tasks. Applied on deploy; nothing happens where the account
does not exist (a developer's own database)."""
from django.db import migrations

EMAILS = ["sachini.n@afitconnect.com"]


def grant(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for email in EMAILS:
        User.objects.filter(email__iexact=email).update(can_delete_tasks=True)


def revoke(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for email in EMAILS:
        User.objects.filter(email__iexact=email).update(can_delete_tasks=False)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_user_can_delete_tasks")]
    operations = [migrations.RunPython(grant, revoke)]
