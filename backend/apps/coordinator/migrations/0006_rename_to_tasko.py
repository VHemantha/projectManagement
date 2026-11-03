from django.db import migrations


def rename_to_tasko(apps, schema_editor):
    """AFIT, 3 Nov 2026: the app is called TASKO. The organisation (if it still has the old default
    name) and the coordinator's account take the new name; past messages are left as they were."""
    Organization = apps.get_model("orgs", "Organization")
    User = apps.get_model("accounts", "User")
    Channel = apps.get_model("chat", "Channel")
    Organization.objects.filter(name="Loca").update(name="TASKO")
    agent = User.objects.filter(email="coordinator@loca.internal").first()
    if agent is not None and not User.objects.filter(email="coordinator@tasko.internal").exists():
        agent.email, agent.display_name = "coordinator@tasko.internal", "TASKO Coordinator"
        if not User.objects.filter(username="tasko-coordinator").exists():
            agent.username = "tasko-coordinator"
        agent.save(update_fields=["email", "display_name", "username"])
    for channel in Channel.objects.filter(name__startswith="loca-coordinator, "):
        channel.name = "tasko-coordinator, " + channel.name[len("loca-coordinator, "):]
        channel.save(update_fields=["name"])


def back_to_loca(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(email="coordinator@tasko.internal").update(email="coordinator@loca.internal", display_name="Loca Coordinator",
                                                                  username="loca-coordinator")


class Migration(migrations.Migration):

    dependencies = [
        ('coordinator', '0005_direct_followups'),
        ('orgs', '0001_initial'),
        ('chat', '0001_initial'),
        ('accounts', '0005_user_is_agent_user_role'),
    ]

    operations = [
        migrations.RunPython(rename_to_tasko, back_to_loca),
    ]
