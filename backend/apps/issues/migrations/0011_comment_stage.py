from django.db import migrations, models

# The AI's results were already posted as comments whose first line names them
# ("AI pre-check — posted automatically on ..."): give those their stage.
TITLE_STAGES = {
    "AI pre-check": "precheck",
    "AI preparation guide": "preparation",
    "AI review": "internal_review",
}


def first_text(body) -> str:
    try:
        return body["content"][0]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return ""


def tag_ai_results(apps, schema_editor):
    Comment = apps.get_model("issues", "Comment")
    for comment in Comment.objects.filter(stage="").iterator():
        text = first_text(comment.body)
        for title, stage in TITLE_STAGES.items():
            if text.startswith(f"{title} — posted automatically"):
                comment.stage = stage
                comment.save(update_fields=["stage"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0010_issue_estimated_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="stage",
            field=models.CharField(
                blank=True,
                choices=[
                    ("precheck", "Pre-check"),
                    ("preparation", "Preparation"),
                    ("internal_review", "Internal review"),
                    ("client_review", "Client review"),
                    ("dispatch", "Dispatch"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.RunPython(tag_ai_results, migrations.RunPython.noop),
    ]
