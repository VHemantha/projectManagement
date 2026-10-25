from django.contrib import admin

from .models import AgentAction, AgentPolicy, AuditEntry, CoordinatorSettings, LeaveRecord, PublicHoliday, WorkSchedule

admin.site.register([CoordinatorSettings, AgentPolicy, AgentAction, WorkSchedule, LeaveRecord, PublicHoliday])


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target", "allowed")
    readonly_fields = [f.name for f in AuditEntry._meta.fields]
