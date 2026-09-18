from django.contrib import admin

from .models import Board, IssueType, Workflow, WorkflowStatus, WorkflowTransition


class WorkflowStatusInline(admin.TabularInline):
    model = WorkflowStatus
    extra = 1


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "project")
    inlines = [WorkflowStatusInline]


@admin.register(IssueType)
class IssueTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "is_subtask", "order")


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "board_type", "swimlane_mode")


admin.site.register(WorkflowTransition)
