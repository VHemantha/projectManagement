from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.orgs.models import Organization
from trackflow.naming import clean_name

from .models import Team, TeamMembership


class TeamMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TeamMembership
        fields = ["id", "user", "user_id", "role", "joined_at"]


class TeamMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "name", "avatar_color"]


class TeamListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    parent = TeamMiniSerializer(read_only=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        source="parent", queryset=Team.objects.all(), write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Team
        fields = ["id", "name", "description", "avatar_color", "member_count", "parent", "parent_id", "created_at"]


class TeamDetailSerializer(serializers.ModelSerializer):
    memberships = TeamMembershipSerializer(many=True, read_only=True)
    parent = TeamMiniSerializer(read_only=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        source="parent", queryset=Team.objects.all(), write_only=True, required=False, allow_null=True
    )
    sub_teams = TeamMiniSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = [
            "id", "name", "description", "avatar_color", "memberships", "parent", "parent_id",
            "sub_teams", "created_at",
        ]

    def validate_name(self, value):
        name = clean_name(value, max_length=Team._meta.get_field("name").max_length, what="Team name")
        clash = Team.objects.filter(name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(f"There's already a team called '{name}'.")
        return name

    def validate_parent_id(self, value):
        if value is None:
            return value
        if self.instance is not None:
            if value.id == self.instance.id:
                raise serializers.ValidationError("A team can't be its own parent.")
            # Walk up from the proposed parent — if we ever hit this instance, the proposed
            # parent is a descendant of this team, which would create a cycle.
            ancestor = value
            while ancestor is not None:
                if ancestor.id == self.instance.id:
                    raise serializers.ValidationError("A team can't be parented under one of its own sub-teams.")
                ancestor = ancestor.parent
        return value

    def create(self, validated_data):
        validated_data["organization"] = Organization.get_solo()
        return super().create(validated_data)
