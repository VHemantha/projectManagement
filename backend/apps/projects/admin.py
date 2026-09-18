from django.contrib import admin

from .models import Component, Label, Project, ProjectCategory, ProjectMembership, Version


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "project_type", "lead", "is_archived", "updated_at")
    search_fields = ("key", "name")
    list_filter = ("project_type", "is_archived")
    inlines = [ProjectMembershipInline]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "color")


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "lead")


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "release_date", "released", "archived")


admin.site.register(ProjectCategory)
