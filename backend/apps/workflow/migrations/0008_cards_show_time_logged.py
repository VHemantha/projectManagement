"""Every board's cards show the time logged on the task, which opens its timesheet breakup (AFIT,
27 Oct 2026). A board that already shows it is left as it is; a team can still switch it off."""
from django.db import migrations


def add_time_logged(apps, schema_editor):
    Board = apps.get_model("workflow", "Board")
    for board in Board.objects.all():
        fields = list(board.card_fields or [])
        if "time_logged" not in fields:
            board.card_fields = fields + ["time_logged"]
            board.save(update_fields=["card_fields"])


class Migration(migrations.Migration):
    dependencies = [("workflow", "0007_afit_stage_columns")]
    operations = [migrations.RunPython(add_time_logged, migrations.RunPython.noop)]
