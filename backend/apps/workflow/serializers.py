from rest_framework import serializers

from .models import Board, IssueType, WorkflowStatus


class WorkflowStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStatus
        fields = ["id", "name", "category", "order"]


class BoardSerializer(serializers.ModelSerializer):
    statuses = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = ["id", "name", "board_type", "column_config", "swimlane_mode", "statuses"]

    def get_statuses(self, obj):
        return WorkflowStatusSerializer(obj.project.workflow.statuses.all(), many=True).data


class IssueTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueType
        fields = ["id", "name", "icon", "color", "is_subtask", "order"]
