from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.services import notify_many
from apps.workflow.models import IssueType

from .filters import IssueFilter
from .models import Attachment, Comment, Issue, IssueHistory, IssueLink, Watcher
from .rank import rank_between
from .serializers import (
    AttachmentSerializer,
    CommentSerializer,
    IssueDetailSerializer,
    IssueHistorySerializer,
    IssueLinkSerializer,
    IssueListSerializer,
    RecentActivitySerializer,
)

KEY_LOOKUP_REGEX = r"[A-Za-z0-9]+-\d+"


class IssueViewSet(viewsets.ModelViewSet):
    queryset = (
        Issue.objects.select_related("project", "issue_type", "status", "assignee", "reporter", "epic", "sprint")
        .prefetch_related("labels")
    )
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "key"
    lookup_value_regex = KEY_LOOKUP_REGEX
    filterset_class = IssueFilter
    search_fields = ["key", "summary"]
    ordering_fields = ["rank", "created_at", "updated_at", "priority", "due_date"]
    ordering = ["rank"]

    def get_serializer_class(self):
        if self.action == "list":
            return IssueListSerializer
        return IssueDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("components", "fix_versions", "subtasks__issue_type", "subtasks__status", "subtasks__assignee")
        return qs

    @action(detail=True, methods=["post"])
    def move(self, request, key=None):
        """Drag-and-drop reorder/move: reposition an issue's rank, and optionally
        change its sprint and/or status in the same call (board + backlog DnD)."""
        issue = self.get_object()
        before_id = request.data.get("before_id")
        after_id = request.data.get("after_id")
        before = Issue.objects.filter(id=before_id).first() if before_id else None
        after = Issue.objects.filter(id=after_id).first() if after_id else None
        issue.rank = rank_between(before.rank if before else None, after.rank if after else None)

        history_rows = []
        if "sprint_id" in request.data:
            old_sprint = issue.sprint
            new_sprint_id = request.data.get("sprint_id")
            issue.sprint_id = new_sprint_id or None
            if issue.sprint_id != (old_sprint.id if old_sprint else None):
                history_rows.append(
                    IssueHistory(
                        issue=issue, user=request.user, field_changed="sprint",
                        old_value=old_sprint.name if old_sprint else "",
                        new_value=issue.sprint.name if issue.sprint_id else "",
                    )
                )
        if "status_id" in request.data:
            old_status = issue.status
            issue.status_id = request.data["status_id"]
            if issue.status_id != old_status.id:
                history_rows.append(
                    IssueHistory(
                        issue=issue, user=request.user, field_changed="status",
                        old_value=str(old_status), new_value=str(issue.status),
                    )
                )
                was_done = old_status.category == "done"
                now_done = issue.status.category == "done"
                if now_done and not was_done:
                    issue.resolved_at = timezone.now()
                elif was_done and not now_done:
                    issue.resolved_at = None

                watcher_ids = issue.watcher_rows.exclude(user=request.user).values_list("user", flat=True)
                notify_many(
                    User.objects.filter(id__in=watcher_ids),
                    Notification.Verb.STATUS_CHANGED,
                    actor=request.user,
                    target_issue=issue,
                )

        issue.save()
        if history_rows:
            IssueHistory.objects.bulk_create(history_rows)
        return Response(IssueDetailSerializer(issue, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post", "delete"])
    def watch(self, request, key=None):
        issue = self.get_object()
        if request.method == "POST":
            Watcher.objects.get_or_create(issue=issue, user=request.user)
        else:
            Watcher.objects.filter(issue=issue, user=request.user).delete()
        return Response({"is_watching": request.method == "POST"})


class IssueCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_issue(self):
        return get_object_or_404(Issue, key__iexact=self.kwargs["issue_key"])

    def get_queryset(self):
        return Comment.objects.filter(issue=self.get_issue()).select_related("author")

    def perform_create(self, serializer):
        issue = self.get_issue()
        serializer.save(issue=issue, author=self.request.user)

        recipients = {u for u in [issue.assignee, issue.reporter] if u}
        watcher_ids = issue.watcher_rows.values_list("user", flat=True)
        recipients |= set(User.objects.filter(id__in=watcher_ids))
        notify_many(recipients, Notification.Verb.COMMENTED, actor=self.request.user, target_issue=issue)


class IssueCommentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Comment.objects.filter(issue__key__iexact=self.kwargs["issue_key"])


class IssueAttachmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get_issue(self):
        return get_object_or_404(Issue, key__iexact=self.kwargs["issue_key"])

    def get_queryset(self):
        return Attachment.objects.filter(issue=self.get_issue()).select_related("uploaded_by")

    def perform_create(self, serializer):
        serializer.save(issue=self.get_issue(), uploaded_by=self.request.user)


class IssueAttachmentDetailView(generics.DestroyAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Attachment.objects.filter(issue__key__iexact=self.kwargs["issue_key"])


class IssueLinkListCreateView(generics.ListCreateAPIView):
    serializer_class = IssueLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_issue(self):
        return get_object_or_404(Issue, key__iexact=self.kwargs["issue_key"])

    def get_queryset(self):
        return IssueLink.objects.filter(source_issue=self.get_issue()).select_related("target_issue")

    def perform_create(self, serializer):
        serializer.save(source_issue=self.get_issue())


class IssueLinkDetailView(generics.DestroyAPIView):
    serializer_class = IssueLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return IssueLink.objects.filter(source_issue__key__iexact=self.kwargs["issue_key"])


class IssueHistoryListView(generics.ListAPIView):
    serializer_class = IssueHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return IssueHistory.objects.filter(issue__key__iexact=self.kwargs["issue_key"]).select_related("user")


class IssueChatLinksView(generics.ListAPIView):
    """Messages linked to this issue (created-from-message or manually linked), surfaced in
    the issue's activity feed alongside Comments/History."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        from apps.chat.serializers import IssueChatLinkSerializer

        return IssueChatLinkSerializer

    def get_queryset(self):
        from apps.chat.models import MessageIssueLink

        return MessageIssueLink.objects.filter(issue__key__iexact=self.kwargs["issue_key"]).select_related(
            "message", "message__author", "message__channel"
        )


class RecentActivityView(generics.ListAPIView):
    """Cross-project activity feed for the dashboard home page."""

    serializer_class = RecentActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return IssueHistory.objects.select_related("user", "issue", "issue__project").order_by("-timestamp")[:20]


class SubtaskCreateView(generics.CreateAPIView):
    """Convenience endpoint for inline "add sub-task" on an issue detail view."""

    serializer_class = IssueDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_parent(self):
        return get_object_or_404(Issue, key__iexact=self.kwargs["issue_key"])

    def create(self, request, *args, **kwargs):
        parent = self.get_parent()
        subtask_type = IssueType.objects.filter(is_subtask=True).first()
        data = {
            **request.data,
            "project": parent.project.key,
            "issue_type_id": subtask_type.id if subtask_type else request.data.get("issue_type_id"),
            "parent_id": parent.id,
            "status_id": request.data.get("status_id", parent.status_id),
        }
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
