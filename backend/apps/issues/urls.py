from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    IssueAttachmentDetailView,
    IssueAttachmentListCreateView,
    IssueChatLinksView,
    IssueCommentDetailView,
    IssueCommentListCreateView,
    IssueHistoryListView,
    IssueLinkDetailView,
    IssueLinkListCreateView,
    IssueViewSet,
    SubtaskCreateView,
)

router = SimpleRouter()
router.register("", IssueViewSet, basename="issue")

urlpatterns = [
    path("<str:issue_key>/comments/", IssueCommentListCreateView.as_view(), name="issue-comments"),
    path("<str:issue_key>/comments/<int:pk>/", IssueCommentDetailView.as_view(), name="issue-comment-detail"),
    path("<str:issue_key>/attachments/", IssueAttachmentListCreateView.as_view(), name="issue-attachments"),
    path(
        "<str:issue_key>/attachments/<int:pk>/",
        IssueAttachmentDetailView.as_view(),
        name="issue-attachment-detail",
    ),
    path("<str:issue_key>/links/", IssueLinkListCreateView.as_view(), name="issue-links"),
    path("<str:issue_key>/links/<int:pk>/", IssueLinkDetailView.as_view(), name="issue-link-detail"),
    path("<str:issue_key>/history/", IssueHistoryListView.as_view(), name="issue-history"),
    path("<str:issue_key>/chat-links/", IssueChatLinksView.as_view(), name="issue-chat-links"),
    path("<str:issue_key>/subtasks/", SubtaskCreateView.as_view(), name="issue-subtasks"),
    path("", include(router.urls)),
]
