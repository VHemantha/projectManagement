from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.hierarchy import UserHierarchyView
from apps.accounts.invitations import InvitationListCreateView, InvitationResendView, InvitationRevokeView
from apps.accounts.views import UserListView
from apps.issues.views import RecentActivityView
from apps.workflow.views import IssueTypeListView


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/hierarchy/", UserHierarchyView.as_view(), name="user-hierarchy"),
    path("invitations/", InvitationListCreateView.as_view(), name="invitation-list"),
    path("invitations/<int:pk>/resend/", InvitationResendView.as_view(), name="invitation-resend"),
    path("invitations/<int:pk>/revoke/", InvitationRevokeView.as_view(), name="invitation-revoke"),
    path("projects/", include("apps.projects.urls")),
    # "Projects" are called "workspaces" in the UI. Same endpoints under the new name, namespaced
    # so URL reversing of the original names is unaffected.
    path("workspaces/", include(("apps.projects.urls", "workspaces"), namespace="workspaces")),
    path("clients/", include("apps.clients.urls")),
    path("issues/", include("apps.issues.urls")),
    path("issue-types/", IssueTypeListView.as_view(), name="issue-type-list"),
    path("sprints/", include("apps.sprints.urls")),
    path("teams/", include("apps.teams.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("search/", include("apps.search.urls")),
    path("activity/recent/", RecentActivityView.as_view(), name="recent-activity"),
    path("chat/", include("apps.chat.urls")),
    path("", include("apps.timesheets.urls")),
    path("", include("apps.workflow.urls")),
    path("reports/", include("apps.reports.urls")),
    path("daily-goals/", include("apps.daily_goals.urls")),
]
