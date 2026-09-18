from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "display_name", "job_title", "is_staff", "is_active")
    search_fields = ("email", "username", "display_name")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "avatar", "job_title", "is_active_member")}),
    )
