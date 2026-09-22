from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.daily_goals.views import TeamDailyGoalsView

from .views import TeamMembershipDetailView, TeamMembershipListCreateView, TeamViewSet

router = SimpleRouter()
router.register("", TeamViewSet, basename="team")

urlpatterns = [
    path("<int:team_id>/members/", TeamMembershipListCreateView.as_view(), name="team-members"),
    path("<int:team_id>/members/<int:pk>/", TeamMembershipDetailView.as_view(), name="team-member-detail"),
    path("<int:team_id>/daily-goals/", TeamDailyGoalsView.as_view(), name="team-daily-goals"),
    path("", include(router.urls)),
]
