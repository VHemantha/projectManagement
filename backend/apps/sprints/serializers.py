from rest_framework import serializers

from .models import Sprint


class SprintSerializer(serializers.ModelSerializer):
    project_key = serializers.CharField(source="project.key", read_only=True)
    issue_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sprint
        fields = [
            "id",
            "project_key",
            "name",
            "goal",
            "start_date",
            "end_date",
            "state",
            "order",
            "issue_count",
            "created_at",
            "completed_at",
        ]
        read_only_fields = ["state", "order", "created_at", "completed_at"]


class SprintStartSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    goal = serializers.CharField(required=False, allow_blank=True)


class SprintCompleteSerializer(serializers.Serializer):
    move_to = serializers.CharField(required=False, default="backlog")
