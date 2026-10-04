from rest_framework import serializers

from apps.teams.models import Team

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    project_count = serializers.SerializerMethodField()
    workspace_project_key = serializers.SerializerMethodField()
    # The workspace (team) this sub-workspace belongs to.
    team_id = serializers.PrimaryKeyRelatedField(
        source="team", queryset=Team.objects.all(), allow_null=True, required=False
    )
    team_name = serializers.CharField(source="team.name", read_only=True, default=None)

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
            "team_id",
            "team_name",
            "project_count",
            "workspace_project_key",
            "created_at",
        ]
