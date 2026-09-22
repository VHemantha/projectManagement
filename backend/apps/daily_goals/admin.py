from django.contrib import admin

from .models import DailyGoal


@admin.register(DailyGoal)
class DailyGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "text", "status")
    list_filter = ("status", "date")
