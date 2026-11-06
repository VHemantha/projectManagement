from django.contrib import admin

from .models import DailyGoal, TodoItem


@admin.register(DailyGoal)
class DailyGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "text", "status")
    list_filter = ("status", "date")


@admin.register(TodoItem)
class TodoItemAdmin(admin.ModelAdmin):
    list_display = ("user", "text", "kind", "due_date", "done")
    list_filter = ("kind", "done")
