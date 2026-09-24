import re

from django.db import transaction
from django.db.models import Count, Max
from rest_framework import serializers

from .models import Board, IssueType, WorkflowStatus, WorkflowTransition

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
STATUS_NAME_MAX = WorkflowStatus._meta.get_field("name").max_length
PRIORITY_KEYS = {"highest", "high", "medium", "low", "lowest"}
DUE_DATE_KEYS = {"overdue", "due_soon", "on_track"}


def status_issue_counts(workflow) -> dict[int, int]:
    """status id -> number of issues currently in that status."""
    from apps.issues.models import Issue  # issues imports workflow models; avoid a cycle

    rows = Issue.objects.filter(status__workflow=workflow).values("status_id").annotate(n=Count("id"))
    return {row["status_id"]: row["n"] for row in rows}


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
            "card_color_rule", "card_colors", "card_color_style", "filters", "statuses",
        ]

    def get_statuses(self, obj):
        # issue_count lets board settings show which statuses are safe to delete, and which
        # unmapped ones would hide issues.
        workflow = obj.project.workflow
        counts = status_issue_counts(workflow)
        data = WorkflowStatusSerializer(workflow.statuses.all(), many=True).data
        for row in data:
            row["issue_count"] = counts.get(row["id"], 0)
        return data


class BoardConfigSerializer(serializers.ModelSerializer):
    """Read/write board configuration — columns, swimlanes, card fields and colour coding.
    Separate from BoardSerializer (which stays read-only/list-shaped with the computed
    `statuses` field) so PATCH payloads can't accidentally touch `name`/`board_type`.

    A column in `column_config` either maps existing statuses (`status_ids`) or, for a brand
    new stage, has no status_ids and carries `new_status: {"category": ...}`: on save a
    workflow status named after the column is created and mapped to it."""

    class Meta:
        model = Board
        fields = [
            "id", "column_config", "swimlane_mode", "card_fields", "card_color_rule",
            "card_colors", "card_color_style", "filters",
        ]

    def validate_column_config(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("column_config must be a list.")
        if not value:
            raise serializers.ValidationError("A board needs at least one column.")
        workflow = self.instance.project.workflow
        statuses = {st.id: st for st in workflow.statuses.all()}
        existing_names = {st.name.lower() for st in statuses.values()}
        categories = set(WorkflowStatus.Category.values)
        cleaned, column_of_status, new_status_names = [], {}, set()

        for i, col in enumerate(value):
            if not isinstance(col, dict) or not isinstance(col.get("name"), str) or not col["name"].strip():
                raise serializers.ValidationError(f"Column {i + 1} needs a name.")
            name = " ".join(col["name"].split())
            status_ids = col.get("status_ids") or []
            if not isinstance(status_ids, list) or not all(isinstance(x, int) for x in status_ids):
                raise serializers.ValidationError(f"Column '{name}' has invalid status_ids.")
            unknown = set(status_ids) - statuses.keys()
            if unknown:
                raise serializers.ValidationError(f"Column '{name}' references unknown status ids: {unknown}")
            for sid in status_ids:
                if sid in column_of_status:
                    raise serializers.ValidationError(
                        f"Status '{statuses[sid].name}' is in both '{column_of_status[sid]}' and '{name}'. "
                        "A status can only be in one column."
                    )
                column_of_status[sid] = name

            row = {"name": name, "status_ids": status_ids, "wip_limit": col.get("wip_limit")}
            if not status_ids:
                new_status = col.get("new_status")
                if not isinstance(new_status, dict) or new_status.get("category") not in categories:
                    raise serializers.ValidationError(
                        f"Column '{name}' needs at least one status. Map an existing one or create a new one."
                    )
                if len(name) > STATUS_NAME_MAX:
                    raise serializers.ValidationError(
                        f"Column '{name}' creates a new status, so its name can be at most {STATUS_NAME_MAX} characters."
                    )
                if name.lower() in existing_names or name.lower() in new_status_names:
                    raise serializers.ValidationError(
                        f"A status named '{name}' already exists. Map it to the column instead of creating a new one."
                    )
                new_status_names.add(name.lower())
                row["new_status"] = {"category": new_status["category"]}

            wip_limit = row["wip_limit"]
            if wip_limit is not None and (
                not isinstance(wip_limit, int) or isinstance(wip_limit, bool) or wip_limit < 1
            ):
                raise serializers.ValidationError(f"Column '{name}' has an invalid wip_limit.")
            color = col.get("color")
            if color is not None:
                if not isinstance(color, str) or not HEX_COLOR.match(color):
                    raise serializers.ValidationError(f"Column '{name}' has an invalid color (use #rrggbb).")
                row["color"] = color.lower()
            cleaned.append(row)

        # An issue whose status isn't on any column silently disappears from the board.
        hidden = [
            f"{statuses[sid].name} ({n} issue{'' if n == 1 else 's'})"
            for sid, n in status_issue_counts(workflow).items()
            if n and sid in statuses and sid not in column_of_status
        ]
        if hidden:
            raise serializers.ValidationError(
                "These statuses still have issues but aren't on any column, so those issues would "
                f"disappear from the board: {', '.join(hidden)}. Map them to a column first."
            )
        return cleaned

    def validate_card_fields(self, value):
        if not isinstance(value, list) or not all(isinstance(f, str) for f in value):
            raise serializers.ValidationError("card_fields must be a list of field-key strings.")
        return value

    def validate_card_colors(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("card_colors must be an object.")
        allowed = {"priority": PRIORITY_KEYS, "due_date": DUE_DATE_KEYS, "issue_type": None}
        cleaned = {}
        for rule, mapping in value.items():
            if rule not in allowed:
                raise serializers.ValidationError(f"Colours can't be customised for '{rule}'.")
            if not isinstance(mapping, dict):
                raise serializers.ValidationError(f"card_colors.{rule} must be an object.")
            keys = allowed[rule]
            for key, color in mapping.items():
                if (keys is not None and key not in keys) or (keys is None and not str(key).isdigit()):
                    raise serializers.ValidationError(f"Unknown {rule} value '{key}'.")
                if not isinstance(color, str) or not HEX_COLOR.match(color):
                    raise serializers.ValidationError(f"Invalid colour for {rule} '{key}' (use #rrggbb).")
            cleaned[rule] = {str(k): c.lower() for k, c in mapping.items()}
        return cleaned

    @transaction.atomic
    def update(self, instance, validated_data):
        columns = validated_data.get("column_config")
        if columns is not None:
            workflow = instance.project.workflow
            next_order = (workflow.statuses.aggregate(m=Max("order"))["m"] or 0) + 1
            for col in columns:
                new_status = col.pop("new_status", None)
                if new_status:
                    status = WorkflowStatus.objects.create(
                        workflow=workflow, name=col["name"], category=new_status["category"], order=next_order
                    )
                    next_order += 1
                    col["status_ids"] = [status.id]
        return super().update(instance, validated_data)


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
