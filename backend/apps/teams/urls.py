from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import TeamMembershipDetailView, TeamMembershipListCreateView, TeamViewSet

router = SimpleRouter()
router.register("", TeamViewSet, basename="team")

urlpatterns = [
    path("<int:team_id>/members/", TeamMembershipListCreateView.as_view(), name="team-members"),
    path("<int:team_id>/members/<int:pk>/", TeamMembershipDetailView.as_view(), name="team-member-detail"),
    path("", include(router.urls)),
]
