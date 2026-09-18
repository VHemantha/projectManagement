from django.contrib import admin

from .models import Attachment, Comment, Issue, IssueHistory, IssueLink, ProjectIssueCounter, Watcher


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("key", "summary", "project", "issue_type", "status", "assignee", "priority", "sprint")
    search_fields = ("key", "summary")
    list_filter = ("project", "issue_type", "status", "priority")


admin.site.register(Comment)
admin.site.register(Attachment)
admin.site.register(IssueLink)
admin.site.register(IssueHistory)
admin.site.register(Watcher)
admin.site.register(ProjectIssueCounter)
