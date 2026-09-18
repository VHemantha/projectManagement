from django.contrib import admin

from .models import BillableRate, TimeEntry, TimeEntryTag, Timesheet


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "issue", "project", "work_date", "duration", "is_billable", "is_running", "locked")
    list_filter = ("is_billable", "is_running", "locked", "created_via")


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    list_display = ("user", "period_start", "period_end", "status", "reviewed_by")
    list_filter = ("status",)


admin.site.register(TimeEntryTag)
admin.site.register(BillableRate)
