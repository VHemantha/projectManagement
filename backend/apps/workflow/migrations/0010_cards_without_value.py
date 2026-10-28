"""The task's value is no longer shown on cards (AFIT, 28 Oct 2026); it stays on the task itself."""
from django.db import migrations


def remove_value(apps, schema_editor):
    Board = apps.get_model("workflow", "Board")
    for board in Board.objects.all():
        fields = list(board.card_fields or [])
        if "job_value" in fields:
            board.card_fields = [f for f in fields if f != "job_value"]
            board.save(update_fields=["card_fields"])


class Migration(migrations.Migration):
    dependencies = [("workflow", "0009_cards_deadline_stage_priority")]
    operations = [migrations.RunPython(remove_value, migrations.RunPython.noop)]
