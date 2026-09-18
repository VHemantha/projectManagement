"""Channel access rules.

Project/team channels derive membership dynamically from ProjectMembership/TeamMembership
(so "always visible to members of that project/team" stays true as membership changes)
rather than requiring a separately-maintained ChannelMembership row for every project/team
member. Manually-created channels (general/topic/DM) use ChannelMembership as the source of
truth for who can see them.
"""
from apps.projects.models import ProjectMembership
from apps.teams.models import TeamMembership

from .models import Channel, ChannelMembership


def user_can_access_channel(user, channel: Channel) -> bool:
    if not user or not user.is_authenticated:
        return False
    if channel.channel_type == Channel.ChannelType.GENERAL:
        return True
    if channel.channel_type == Channel.ChannelType.PROJECT:
        project = channel.linked_project
        if project.lead_id == user.id:
            return True
        return ProjectMembership.objects.filter(project=project, user=user).exists()
    if channel.channel_type == Channel.ChannelType.TEAM:
        return TeamMembership.objects.filter(team=channel.linked_team, user=user).exists()
    return ChannelMembership.objects.filter(channel=channel, user=user).exists()


def ensure_channel_membership(user, channel: Channel) -> ChannelMembership:
    """Lazily create the per-user ChannelMembership row (last_read_at, muted, ...) the first
    time a project/team-derived member actually opens the channel."""
    membership, _ = ChannelMembership.objects.get_or_create(channel=channel, user=user)
    return membership
