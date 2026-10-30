"""AFIT, 29 Oct 2026: a column holding one stage gives that stage its name (columns renamed in the
board settings had left their cards showing the old stage name); and cards show the Accountant's
badge instead of the Team Lead's."""
from django.db import migrations

from apps.workflow.services import stage_name_changes


def forwards(apps, schema_editor):
    Board = apps.get_model("workflow", "Board")
    WorkflowStatus = apps.get_model("workflow", "WorkflowStatus")
    for board in Board.objects.select_related("project"):
        statuses = list(WorkflowStatus.objects.filter(workflow__project_id=board.project_id))
        for status, name in stage_name_changes(board.column_config, statuses):
            status.name = name
            status.save(update_fields=["name"])
        fields = list(board.card_fields or [])
        if "assignee" in fields:
            board.card_fields = list(dict.fromkeys("accountant" if f == "assignee" else f for f in fields))
            board.save(update_fields=["card_fields"])


class Migration(migrations.Migration):
    dependencies = [("workflow", "0011_boards_without_swimlanes")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
