"""Shared rules for names people type (teams, workspaces, columns, labels, channels, filters)."""
from rest_framework import serializers


def clean_name(value, *, max_length: int, what: str = "Name") -> str:
    """Collapse runs of whitespace; reject empty or over-long names."""
    name = " ".join(str(value or "").split())
    if not name:
        raise serializers.ValidationError(f"{what} can't be empty.")
    if len(name) > max_length:
        raise serializers.ValidationError(f"{what} can be at most {max_length} characters.")
    return name
