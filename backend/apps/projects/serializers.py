import re

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.orgs.models import Organization

from .models import Component, KEY_PATTERN, Label, Project, ProjectMembership, Version


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
            "created_at",
            "updated_at",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    key = serializers.CharField(max_length=10)
    lead = UserSerializer(read_only=True)
    lead_id = serializers.IntegerField(write_only=True, required=False)
    memberships = ProjectMembershipSerializer(many=True, read_only=True)
    labels = LabelSerializer(many=True, read_only=True)
    components = ComponentSerializer(many=True, read_only=True)
    versions = VersionSerializer(many=True, read_only=True)

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
            "created_at",
            "updated_at",
        ]

    def validate_key(self, value):
        value = value.upper()
        if not re.match(KEY_PATTERN, value):
            raise serializers.ValidationError(
                "Project key must be 2-10 letters/digits, starting with a letter."
            )
        qs = Project.objects.filter(key=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A project with this key already exists.")
        return value

    def create(self, validated_data):
        lead_id = validated_data.pop("lead_id", None)
        request = self.context["request"]
        validated_data["organization"] = Organization.get_solo()
        if lead_id:
            validated_data["lead_id"] = lead_id
        else:
            validated_data["lead"] = request.user
        project = Project.objects.create(**validated_data)
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
        if lead_id:
            instance.lead_id = lead_id
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
