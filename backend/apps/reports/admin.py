from django.contrib import admin

from .models import Dashboard, DashboardWidget


class DashboardWidgetInline(admin.TabularInline):
    model = DashboardWidget
    extra = 1


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_default")
    inlines = [DashboardWidgetInline]
