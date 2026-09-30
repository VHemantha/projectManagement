from django.db import migrations


def show_job_value_on_cards(apps, schema_editor):
    # Existing boards get the new "Job value" card field too, so value can be entered on cards
    # straight away; each board can still turn it off in board settings.
    Board = apps.get_model("workflow", "Board")
    for board in Board.objects.all():
        fields = list(board.card_fields or [])
        if "job_value" not in fields:
            board.card_fields = fields + ["job_value"]
            board.save(update_fields=["card_fields"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0004_sentence_case_statuses"),
    ]

    operations = [
        migrations.RunPython(show_job_value_on_cards, migrations.RunPython.noop),
    ]
