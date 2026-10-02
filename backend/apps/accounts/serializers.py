from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "display_name", "job_title", "avatar", "is_staff"]
        read_only_fields = ["id", "email", "is_staff"]


class MeSerializer(UserSerializer):
    """The signed-in user's own profile, including their personal settings."""

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "desktop_notifications"]


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    # Sign-up is by invitation only; the account's email comes from the invitation.
    invite_token = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False)

    class Meta:
        model = User
        fields = ["email", "username", "password", "display_name", "job_title", "invite_token"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop("invite_token", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
