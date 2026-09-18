from django.urls import path

from .views import (
    SprintCompleteView,
    SprintDetailView,
    SprintListCreateView,
    SprintStartView,
    reorder_sprints,
    sprint_burndown,
    velocity,
)

urlpatterns = [
    path("<int:pk>/", SprintDetailView.as_view(), name="sprint-detail"),
    path("<int:pk>/start/", SprintStartView.as_view(), name="sprint-start"),
    path("<int:pk>/complete/", SprintCompleteView.as_view(), name="sprint-complete"),
    path("<int:pk>/burndown/", sprint_burndown, name="sprint-burndown"),
]

project_urlpatterns = [
    path("<str:project_key>/sprints/", SprintListCreateView.as_view(), name="project-sprints"),
    path("<str:project_key>/sprints/reorder/", reorder_sprints, name="project-sprints-reorder"),
    path("<str:project_key>/velocity/", velocity, name="project-velocity"),
]
