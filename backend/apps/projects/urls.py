from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.sprints.urls import project_urlpatterns as sprint_project_urlpatterns
from apps.workflow.views import WorkflowTransitionListView

from .views import (
    ComponentListCreateView,
    LabelListCreateView,
    ProjectMembershipDetailView,
    ProjectMembershipListCreateView,
    ProjectViewSet,
    VersionListCreateView,
)

router = SimpleRouter()
router.register("", ProjectViewSet, basename="project")

urlpatterns = [
    path("<str:project_key>/members/", ProjectMembershipListCreateView.as_view(), name="project-members"),
    path(
        "<str:project_key>/members/<int:pk>/",
        ProjectMembershipDetailView.as_view(),
        name="project-member-detail",
    ),
    path("<str:project_key>/labels/", LabelListCreateView.as_view(), name="project-labels"),
    path("<str:project_key>/components/", ComponentListCreateView.as_view(), name="project-components"),
    path("<str:project_key>/versions/", VersionListCreateView.as_view(), name="project-versions"),
    path(
        "<str:project_key>/workflow/transitions/",
        WorkflowTransitionListView.as_view(),
        name="project-workflow-transitions",
    ),
    *sprint_project_urlpatterns,
    path("", include(router.urls)),
]
