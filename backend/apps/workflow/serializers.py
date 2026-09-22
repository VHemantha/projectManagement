from rest_framework import serializers

from .models import Board, IssueType, WorkflowStatus, WorkflowTransition


class WorkflowStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStatus
        fields = ["id", "name", "category", "order"]


class BoardSerializer(serializers.ModelSerializer):
    statuses = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = [
            "id", "name", "board_type", "column_config", "swimlane_mode", "card_fields",
            "card_color_rule", "filters", "statuses",
        ]

    def get_statuses(self, obj):
        return WorkflowStatusSerializer(obj.project.workflow.statuses.all(), many=True).data


class BoardConfigSerializer(serializers.ModelSerializer):
    """Read/write board configuration — column layout, swimlanes, card fields. Separate from
    BoardSerializer (which stays read-only/list-shaped with the computed `statuses` field) so
    PATCH payloads can't accidentally touch `name`/`board_type`."""

    class Meta:
        model = Board
        fields = ["id", "column_config", "swimlane_mode", "card_fields", "card_color_rule", "filters"]

    def validate_column_config(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("column_config must be a list.")
        valid_status_ids = set(self.instance.project.workflow.statuses.values_list("id", flat=True))
        for i, col in enumerate(value):
            if not isinstance(col, dict) or "name" not in col:
                raise serializers.ValidationError(f"Column {i} must be an object with a 'name'.")
            status_ids = col.get("status_ids") or []
            if not status_ids:
                raise serializers.ValidationError(
                    f"Column '{col['name']}' needs at least one status — cards can't be moved into an empty column."
                )
            unknown = set(status_ids) - valid_status_ids
            if unknown:
                raise serializers.ValidationError(f"Column '{col['name']}' references unknown status ids: {unknown}")
            wip_limit = col.get("wip_limit")
            if wip_limit is not None and (not isinstance(wip_limit, int) or wip_limit < 1):
                raise serializers.ValidationError(f"Column '{col['name']}' has an invalid wip_limit.")
        return value

    def validate_card_fields(self, value):
        if not isinstance(value, list) or not all(isinstance(f, str) for f in value):
            raise serializers.ValidationError("card_fields must be a list of field-key strings.")
        return value


class WorkflowTransitionSerializer(serializers.ModelSerializer):
    from_status_name = serializers.CharField(source="from_status.name", read_only=True, default="Any")
    to_status_name = serializers.CharField(source="to_status.name", read_only=True)

    class Meta:
        model = WorkflowTransition
        fields = [
            "id", "name", "from_status", "from_status_name", "to_status", "to_status_name",
            "set_current_responsible_to",
        ]
        # Transitions are structural to the workflow (created by workflow provisioning, not
        # editable via this addendum's minimal UI) — only the auto-reassign rule is writable.
        read_only_fields = ["name", "from_status", "to_status"]


class IssueTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueType
        fields = ["id", "name", "icon", "color", "is_subtask", "order"]
