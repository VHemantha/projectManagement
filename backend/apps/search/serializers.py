from rest_framework import serializers

from trackflow.naming import clean_name

from .models import Filter


class FilterSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)

    class Meta:
        model = Filter
        fields = ["id", "name", "owner", "owner_name", "query", "is_public", "created_at", "updated_at"]
        read_only_fields = ["owner"]

    def validate_name(self, value):
        name = clean_name(value, max_length=Filter._meta.get_field("name").max_length, what="Filter name")
        owner = self.instance.owner if self.instance else self.context["request"].user
        clash = Filter.objects.filter(owner=owner, name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(f"You already have a filter called '{name}'.")
        return name
