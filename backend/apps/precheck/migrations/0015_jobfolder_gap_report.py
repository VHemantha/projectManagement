from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("precheck", "0014_wp_agent_wages_ica"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobfolder",
            name="gap_report",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="jobfolder",
            name="gap_report_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
