from django.urls import path

from .views import (
    FindingDispositionView,
    InternalEventView,
    InternalJobView,
    JobPrecheckView,
    JobSetupView,
    RunDetailView,
    RunListView,
)

urlpatterns = [
    path("jobs/<str:key>/", JobPrecheckView.as_view(), name="precheck-job"),
    path("jobs/<str:key>/setup/", JobSetupView.as_view(), name="precheck-setup"),
    path("runs/", RunListView.as_view(), name="precheck-runs"),
    path("runs/<str:run_id>/", RunDetailView.as_view(), name="precheck-run"),
    path("findings/<int:pk>/disposition/", FindingDispositionView.as_view(), name="precheck-disposition"),
    path("internal/jobs/<int:issue_id>/", InternalJobView.as_view(), name="precheck-internal-job"),
    path("internal/events/", InternalEventView.as_view(), name="precheck-internal-events"),
]
