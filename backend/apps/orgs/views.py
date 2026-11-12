"""The organisation's own record and the CEO's editing of names across it (AFIT, 12 Nov 2026).

GET   /api/organization/              the organisation's name (anyone signed in: the sidebar shows it)
PATCH /api/organization/  {name}      rename it (CEO only)
PATCH /api/users/<id>/    {display_name?, job_title?}   rename a person (CEO only)

Workspaces, sub-workspaces and projects are renamed through their own endpoints, which already let
an organisation admin (the CEO is one) do it. Every change here is written to the coordinator's audit
log, and a refused attempt is logged too.
"""
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.coordinator import services
from apps.live.broadcast import notify
from trackflow.naming import clean_name

from .models import Organization


class OrganizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = Organization.get_solo()
        return Response({"id": org.id, "name": org.name, "can_edit": services.is_ceo(request.user)})

    def patch(self, request):
        services.require_ceo(request.user, "rename organisation")
        org = Organization.get_solo()
        try:
            name = clean_name(request.data.get("name"), max_length=Organization._meta.get_field("name").max_length,
                              what="The organisation's name")
        except serializers.ValidationError as exc:
            return Response({"name": exc.detail}, status=400)
        before = org.name
        if name != before:
            org.name = name
            org.save(update_fields=["name"])
            services.audit(request.user, "rename organisation", name, before=before, after=name)
            notify("teams")  # every open tab refreshes the sidebar's name
        return Response({"id": org.id, "name": org.name, "can_edit": True})


class PersonNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["display_name", "job_title"]

    def validate_display_name(self, value):
        return clean_name(value, max_length=User._meta.get_field("display_name").max_length, what="A person's name")

    def validate_job_title(self, value):
        return " ".join(str(value or "").split())[: User._meta.get_field("job_title").max_length]


class PersonNameView(APIView):
    """The CEO renames anyone (their own name stays editable on their profile page)."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        services.require_ceo(request.user, "rename person", f"user {pk}")
        person = User.objects.filter(pk=pk, is_agent=False).first()
        if person is None:
            return Response({"detail": "No such person."}, status=404)
        serializer = PersonNameSerializer(person, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {f: getattr(person, f) for f in serializer.validated_data}
        serializer.save()
        after = {f: getattr(person, f) for f in serializer.validated_data}
        if before != after:
            services.audit(request.user, "rename person", person.email, before=before, after=after)
            notify("teams")  # the People page and org chart list people by team
        return Response(UserSerializer(person, context={"request": request}).data)
