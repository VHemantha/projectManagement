from django.conf import settings
from django.db import models


class Channel(models.Model):
    class ChannelType(models.TextChoices):
        PROJECT = "project", "Project"
        TEAM = "team", "Team"
        DIRECT_MESSAGE = "direct_message", "Direct message"
        GROUP_DM = "group_dm", "Group DM"
        GENERAL = "general", "General"
        TOPIC = "topic", "Topic"

    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="channels"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    channel_type = models.CharField(max_length=20, choices=ChannelType.choices)
    linked_project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="channels"
    )
    linked_team = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.CASCADE, related_name="channels"
    )
    is_private = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_channels"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ChannelMembership", related_name="channels"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"#{self.name}"

    @property
    def is_archived(self):
        return self.archived_at is not None


class ChannelMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    class NotificationPreference(models.TextChoices):
        ALL = "all", "All messages"
        MENTIONS_ONLY = "mentions_only", "Mentions only"
        NONE = "none", "None"

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channel_memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    muted = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(null=True, blank=True)
    notification_preference = models.CharField(
        max_length=20, choices=NotificationPreference.choices, default=NotificationPreference.ALL
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("channel", "user")

    def __str__(self):
        return f"{self.user} in {self.channel}"


class Message(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages")
    body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    parent_message = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    pinned = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["channel", "created_at"])]

    def __str__(self):
        return f"Message from {self.author} in {self.channel}"


class MessageReaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    emoji = models.CharField(max_length=8)

    class Meta:
        unique_together = ("message", "user", "emoji")


class MessageIssueLink(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="issue_links")
    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="chat_links")
    created_task = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "issue")

    def __str__(self):
        verb = "created" if self.created_task else "linked to"
        return f"{self.message_id} {verb} {self.issue.key}"


class MessageMention(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_mentions"
    )

    class Meta:
        unique_together = ("message", "mentioned_user")
