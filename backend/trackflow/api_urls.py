from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
    path("projects/", include("apps.projects.urls")),
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
