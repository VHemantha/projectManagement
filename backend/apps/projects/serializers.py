import re

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.accounts.serializers import UserSerializer
from apps.clients.models import Client
from apps.orgs.models import Organization
from apps.teams.models import Team
from trackflow.naming import clean_name

from .keys import key_in_use, rename_project_key
from .models import Component, KEY_PATTERN, Label, Project, ProjectMembership, Version
from .permissions import can_manage_project


# A task name becomes an issue summary, so it shares Issue.summary's max_length.
MAX_TASK_NAME_LENGTH = 500
MAX_TASK_NAMES = 200

# Fields only workspace managers may change: its name and key, and the dashboard panel's
# budget, deadline, description and notes.
MANAGED_FIELDS = frozenset({"name", "key", "budgeted_hours", "deadline", "description", "special_notes"})

class ClientMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "name"]


class TeamMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "name", "avatar_color"]


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ProjectMembership
        fields = ["id", "user", "user_id", "role", "joined_at"]


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name", "color"]

    def validate_name(self, value):
        name = clean_name(value, max_length=Label._meta.get_field("name").max_length, what="Label name")
        project = self.instance.project if self.instance else self.context.get("project")
        if project is not None:
            clash = Label.objects.filter(project=project, name__iexact=name)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(f"This workspace already has a label called '{name}'.")
        return name

    def validate_color(self, value):
        if not re.match(r"^#[0-9a-fA-F]{6}$", value or ""):
            raise serializers.ValidationError("Use a colour like #a1b2c3.")
        return value


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Component
        fields = ["id", "name", "description", "lead"]


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Version
        fields = ["id", "name", "description", "release_date", "released", "archived"]


class ProjectListSerializer(serializers.ModelSerializer):
    lead = UserSerializer(read_only=True)
    issue_count = serializers.IntegerField(read_only=True)
    client = ClientMiniSerializer(read_only=True)
    primary_team = TeamMiniSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "key",
            "name",
            "description",
            "project_type",
            "lead",
            "avatar_color",
            "is_archived",
            "issue_count",
            "client",
            "primary_team",
            "is_client_workspace",
            "created_at",
            "updated_at",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    key = serializers.CharField(max_length=100)
    lead = UserSerializer(read_only=True)
    lead_id = serializers.IntegerField(write_only=True, required=False)
    memberships = ProjectMembershipSerializer(many=True, read_only=True)
    labels = LabelSerializer(many=True, read_only=True)
    components = ComponentSerializer(many=True, read_only=True)
    versions = VersionSerializer(many=True, read_only=True)
    client = ClientMiniSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        source="client", queryset=Client.objects.all(), write_only=True, required=False, allow_null=True
    )
    primary_team = TeamMiniSerializer(read_only=True)
    primary_team_id = serializers.PrimaryKeyRelatedField(
        source="primary_team", queryset=Team.objects.all(), write_only=True, required=False, allow_null=True
    )
    contributing_teams = TeamMiniSerializer(many=True, read_only=True)
    contributing_team_ids = serializers.PrimaryKeyRelatedField(
        source="contributing_teams", queryset=Team.objects.all(), many=True, write_only=True, required=False
    )
    # Hours logged against the workspace's jobs, for the dashboard panel's budget bar.
    actual_hours = serializers.SerializerMethodField()
    # Whether the requesting user may edit the managed fields (see MANAGED_FIELDS).
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "key",
            "name",
            "description",
            "project_type",
            "lead",
            "lead_id",
            "avatar_color",
            "default_assignee_rule",
            "is_archived",
            "memberships",
            "labels",
            "components",
            "versions",
            "client",
            "client_id",
            "primary_team",
            "primary_team_id",
            "contributing_teams",
            "contributing_team_ids",
            "budgeted_hours",
            "actual_hours",
            "deadline",
            "special_notes",
            "can_manage",
            "job_value",
            "job_value_currency",
            "task_names",
            "is_client_workspace",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_client_workspace"]

    def get_actual_hours(self, obj) -> float:
        from apps.timesheets.budget import project_actual_hours

        return project_actual_hours(obj.id)

    def get_can_manage(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and can_manage_project(request.user, obj))

    def validate_name(self, value):
        return clean_name(value, max_length=Project._meta.get_field("name").max_length, what="Workspace name")

    def validate_budgeted_hours(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Budgeted hours can't be negative.")
        return value

    def validate(self, attrs):
        # Name, key, budget, deadline, description and notes are the workspace managers' to
        # change; everyone else sees them read-only.
        request = self.context.get("request")
        if self.instance is not None and request is not None:
            # Unchanged values are fine: forms send every field back.
            touched = {f for f in MANAGED_FIELDS.intersection(attrs) if attrs[f] != getattr(self.instance, f)}
            if touched and not can_manage_project(request.user, self.instance):
                raise PermissionDenied(
                    "Only the workspace lead, a workspace admin or an organisation admin can change "
                    + ", ".join(sorted(f.replace("_", " ") for f in touched))
                    + "."
                )
        return attrs

    def validate_task_names(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError("Must be a list of task names.")
        cleaned, seen = [], set()
        for name in value:
            name = " ".join(name.split())
            if not name or name.lower() in seen:
                continue
            if len(name) > MAX_TASK_NAME_LENGTH:
                raise serializers.ValidationError(
                    f"Task names can be at most {MAX_TASK_NAME_LENGTH} characters."
                )
            seen.add(name.lower())
            cleaned.append(name)
        if len(cleaned) > MAX_TASK_NAMES:
            raise serializers.ValidationError(f"A workspace can have at most {MAX_TASK_NAMES} tasks.")
        return cleaned

    def validate_key(self, value):
        # Kept as typed ("Pochin"); unique ignoring case, including other projects' old keys.
        value = value.strip()
        if not re.match(KEY_PATTERN, value):
            raise serializers.ValidationError(
                "Workspace key must be 2-100 letters/digits, starting with a letter."
            )
        if key_in_use(value, exclude_project=self.instance):
            raise serializers.ValidationError("That key is already used by another workspace.")
        return value

    def create(self, validated_data):
        lead_id = validated_data.pop("lead_id", None)
        # contributing_teams is a many-to-many (through ProjectTeam) — it can't be passed to
        # Model.objects.create() before the instance has a PK, so it's set separately below.
        contributing_teams = validated_data.pop("contributing_teams", None)
        request = self.context["request"]
        validated_data["organization"] = Organization.get_solo()
        if lead_id:
            validated_data["lead_id"] = lead_id
        else:
            validated_data["lead"] = request.user
        project = Project.objects.create(**validated_data)
        if contributing_teams is not None:
            project.contributing_teams.set(contributing_teams)
        ProjectMembership.objects.get_or_create(
            project=project, user=project.lead, defaults={"role": ProjectMembership.Role.ADMIN}
        )
        if project.lead_id != request.user.id:
            ProjectMembership.objects.get_or_create(
                project=project, user=request.user, defaults={"role": ProjectMembership.Role.ADMIN}
            )
        return project

    def update(self, instance, validated_data):
        lead_id = validated_data.pop("lead_id", None)
        contributing_teams = validated_data.pop("contributing_teams", None)
        new_key = validated_data.pop("key", None)
        if new_key and new_key != instance.key:
            rename_project_key(instance, new_key)  # also re-keys every job
        if lead_id:
            instance.lead_id = lead_id
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if contributing_teams is not None:
            instance.contributing_teams.set(contributing_teams)
        return instance
