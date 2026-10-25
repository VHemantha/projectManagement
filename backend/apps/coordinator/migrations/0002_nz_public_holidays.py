"""New Zealand's national public holidays for 2026 and 2027 (the CEO adds the regional anniversary
day and later years in the coordinator console)."""
from datetime import date

from django.db import migrations


def load(apps, schema_editor):
    from apps.coordinator.calendar import NZ_HOLIDAYS

    PublicHoliday = apps.get_model("coordinator", "PublicHoliday")
    for day, name in NZ_HOLIDAYS:
        PublicHoliday.objects.get_or_create(date=date.fromisoformat(day), defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("coordinator", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
