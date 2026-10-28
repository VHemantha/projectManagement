"""Boards have no swimlanes (AFIT, 28 Oct 2026): every saved board setting goes back to none."""
from django.db import migrations


def no_swimlanes(apps, schema_editor):
    apps.get_model("workflow", "Board").objects.exclude(swimlane_mode="none").update(swimlane_mode="none")


class Migration(migrations.Migration):
    dependencies = [("workflow", "0010_cards_without_value")]
    operations = [migrations.RunPython(no_swimlanes, migrations.RunPython.noop)]
