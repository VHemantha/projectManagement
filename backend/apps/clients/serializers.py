from rest_framework import serializers

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    project_count = serializers.SerializerMethodField()
    workspace_project_key = serializers.SerializerMethodField()

    def get_project_count(self, obj):
        # Real projects only — the automatic job container isn't one the user created.
        return obj.projects.filter(is_client_workspace=False).count()

    def get_workspace_project_key(self, obj):
        workspace = obj.projects.filter(is_client_workspace=True).first()
        return workspace.key if workspace else None

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "logo",
            "primary_contact_name",
            "primary_contact_email",
            "notes",
            "requires_projects",
            "project_count",
            "workspace_project_key",
            "created_at",
        ]
