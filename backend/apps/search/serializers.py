from rest_framework import serializers

from .models import Filter


class FilterSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)

    class Meta:
        model = Filter
        fields = ["id", "name", "owner", "owner_name", "query", "is_public", "created_at", "updated_at"]
        read_only_fields = ["owner"]
