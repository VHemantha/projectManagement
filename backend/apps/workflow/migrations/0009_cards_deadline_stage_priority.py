"""Every card shows the deadline, stage and priority, and no longer the time logged or story points
(AFIT, 28 Oct 2026). Those are part of the card now, so they come out of each board's optional
card fields, along with the removed ones."""
from django.db import migrations

DROPPED = {"story_points", "time_logged", "priority", "due_date"}


def tidy_card_fields(apps, schema_editor):
    Board = apps.get_model("workflow", "Board")
    for board in Board.objects.all():
        fields = list(board.card_fields or [])
        kept = [f for f in fields if f not in DROPPED]
        if kept != fields:
            board.card_fields = kept
            board.save(update_fields=["card_fields"])


class Migration(migrations.Migration):
    dependencies = [("workflow", "0008_cards_show_time_logged")]
    operations = [migrations.RunPython(tidy_card_fields, migrations.RunPython.noop)]
