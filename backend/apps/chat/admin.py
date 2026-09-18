from django.contrib import admin

from .models import Channel, ChannelMembership, Message, MessageIssueLink, MessageMention, MessageReaction


class ChannelMembershipInline(admin.TabularInline):
    model = ChannelMembership
    extra = 1


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "channel_type", "linked_project", "linked_team", "is_private", "archived_at")
    list_filter = ("channel_type", "is_private")
    inlines = [ChannelMembershipInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("channel", "author", "created_at", "pinned", "is_system")
    list_filter = ("pinned", "is_system")


admin.site.register(MessageReaction)
admin.site.register(MessageIssueLink)
admin.site.register(MessageMention)
