"""Team 3 > Local's cards use the Local Tax workflow (AFIT, 22 Nov 2026). Only that sub-workspace."""
from django.db import migrations


def mark(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    Client.objects.filter(name__iexact="Local", team__name__iexact="Team 3").update(workflow="local_tax")


def unmark(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    Client.objects.filter(workflow="local_tax").update(workflow="")


class Migration(migrations.Migration):
    dependencies = [("clients", "0004_client_workflow")]
    operations = [migrations.RunPython(mark, unmark)]
