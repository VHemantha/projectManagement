from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.orgs.models import Organization

from .models import Team, TeamMembership


class TeamMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TeamMembership
        fields = ["id", "user", "user_id", "role", "joined_at"]


class TeamListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "description", "avatar_color", "member_count", "created_at"]


class TeamDetailSerializer(serializers.ModelSerializer):
    memberships = TeamMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "description", "avatar_color", "memberships", "created_at"]

    def create(self, validated_data):
        validated_data["organization"] = Organization.get_solo()
        return super().create(validated_data)
