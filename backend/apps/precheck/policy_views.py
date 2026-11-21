"""The pre-check policies API (AFIT, 20 Nov 2026).

GET  /api/precheck/policies/?task=KEY&q=&scope=   the policies (with ?task=, those that apply to that task)
POST /api/precheck/policies/                       {scope, client_id | group | location, precheck_type, title, text}
GET/PATCH/DELETE /api/precheck/policies/<id>/      one policy (PATCH: any field, or {active})
POST /api/precheck/policies/<id>/feedback/         {text, task?, context?}: the AI revises the policy from it

Any member of staff (the accountants) writes a policy; its author, a lead or an admin changes or
deletes it. Anyone may give feedback, which the AI turns into a revision; the old wording is kept.
"""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from . import policies as PL
from . import services
from .models import PrecheckPolicy
from .views import _job


def _can_change(user, policy: PrecheckPolicy) -> bool:
    return bool(user.is_staff or policy.created_by_id == user.id or services.can_add_rules(user))


class PolicyListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        task = request.query_params.get("task")
        qs = PrecheckPolicy.objects.select_related("client", "created_by", "updated_by")
        if task:
            issue = _job(request, task)
            ids = [p["id"] for p in PL.policies_for(issue)]
            qs = qs.filter(id__in=ids)
        if q := " ".join(str(request.query_params.get("q") or "").split()):
            qs = qs.filter(Q(title__icontains=q) | Q(text__icontains=q) | Q(group__icontains=q) | Q(location__icontains=q) | Q(client__name__icontains=q))
        if (scope := request.query_params.get("scope")) in PrecheckPolicy.Scope.values:
            qs = qs.filter(scope=scope)
        return Response({"policies": [{**PL.policy_dict(p), "can_change": _can_change(request.user, p)} for p in qs[:500]], **PL.options()})

    def post(self, request):
        fields, errors = PL.clean_input(request.data)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        policy = PrecheckPolicy.objects.create(**fields, created_by=request.user, updated_by=request.user)
        return Response({**PL.policy_dict(policy, with_feedback=True), "can_change": True}, status=status.HTTP_201_CREATED)


class PolicyDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, pk):
        return get_object_or_404(PrecheckPolicy.objects.select_related("client", "created_by", "updated_by"), pk=pk)

    def get(self, request, pk):
        policy = self._get(pk)
        return Response({**PL.policy_dict(policy, with_feedback=True), "can_change": _can_change(request.user, policy)})

    def patch(self, request, pk):
        policy = self._get(pk)
        if not _can_change(request.user, policy):
            raise PermissionDenied("Only the policy's author, a lead or an admin can change it.")
        fields, errors = PL.clean_input(request.data, current=policy)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        title, text = fields.pop("title"), fields.pop("text")
        PL.save_wording(policy, title=title, text=text, by=request.user, why="Edited.")
        for k, v in fields.items():
            setattr(policy, k, v)
        policy.updated_by = request.user
        policy.save()
        return Response({**PL.policy_dict(policy, with_feedback=True), "can_change": True})

    def delete(self, request, pk):
        policy = self._get(pk)
        if not _can_change(request.user, policy):
            raise PermissionDenied("Only the policy's author, a lead or an admin can delete it.")
        policy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PolicyFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        policy = get_object_or_404(PrecheckPolicy.objects.select_related("client"), pk=pk)
        text = " ".join(str(request.data.get("text") or "").split())
        if len(text) < 3:
            return Response({"text": ["Say what should change in the policy."]}, status=status.HTTP_400_BAD_REQUEST)
        issue = _job(request, str(request.data["task"])) if request.data.get("task") else None
        context = " ".join(str(request.data.get("context") or "").split())
        fb = PL.give_feedback(policy, request.user, text, issue=issue, context=context)
        return Response(PL.feedback_dict(fb), status=status.HTTP_201_CREATED)
