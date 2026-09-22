from rest_framework import serializers

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    project_count = serializers.IntegerField(source="projects.count", read_only=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "logo",
            "primary_contact_name",
            "primary_contact_email",
            "notes",
            "project_count",
            "created_at",
        ]
