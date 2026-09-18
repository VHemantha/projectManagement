from django.contrib import admin

from .models import Filter


@admin.register(Filter)
class FilterAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_public", "updated_at")
