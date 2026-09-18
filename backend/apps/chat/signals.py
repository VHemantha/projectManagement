from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.projects.models import Project
from apps.teams.models import Team

from .models import Channel, ChannelMembership


@receiver(post_save, sender=Project)
def create_project_channel(sender, instance, created, **kwargs):
    if not created:
        return
    channel = Channel.objects.create(
        organization=instance.organization,
        name=instance.key.lower(),
        description=f"Discussion for {instance.name}",
        channel_type=Channel.ChannelType.PROJECT,
        linked_project=instance,
        created_by=instance.lead,
    )
    if instance.lead:
        ChannelMembership.objects.get_or_create(
            channel=channel, user=instance.lead, defaults={"role": ChannelMembership.Role.OWNER}
        )


@receiver(post_save, sender=Team)
def create_team_channel(sender, instance, created, **kwargs):
    if not created:
        return
    Channel.objects.create(
        organization=instance.organization,
        name=instance.name.lower().replace(" ", "-"),
        description=f"Discussion for {instance.name}",
        channel_type=Channel.ChannelType.TEAM,
        linked_team=instance,
    )


def archive_channels_for_project(project):
    """Called by a project-archive action if/when one is added to ProjectViewSet;
    channels are archived (kept, read-only) rather than deleted, per spec."""
    Channel.objects.filter(linked_project=project, archived_at__isnull=True).update(archived_at=timezone.now())


def archive_channels_for_team(team):
    Channel.objects.filter(linked_team=team, archived_at__isnull=True).update(archived_at=timezone.now())
