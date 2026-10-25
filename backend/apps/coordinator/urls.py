from django.urls import path

from .views import (
    ActionsView,
    AuditView,
    CaseListView,
    HolidayListView,
    LeaveDetailView,
    LeaveListView,
    MeView,
    PolicyListView,
    ScheduleView,
    SettingsView,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="coordinator-me"),
    path("settings/", SettingsView.as_view(), name="coordinator-settings"),
    path("policies/", PolicyListView.as_view(), name="coordinator-policies"),
    path("audit/", AuditView.as_view(), name="coordinator-audit"),
    path("actions/", ActionsView.as_view(), name="coordinator-actions"),
    path("cases/", CaseListView.as_view(), name="coordinator-cases"),
    path("leave/", LeaveListView.as_view(), name="coordinator-leave"),
    path("leave/<int:pk>/", LeaveDetailView.as_view(), name="coordinator-leave-detail"),
    path("leave/<int:pk>/decide/", LeaveDetailView.as_view(), name="coordinator-leave-decide"),
    path("holidays/", HolidayListView.as_view(), name="coordinator-holidays"),
    path("schedules/", ScheduleView.as_view(), name="coordinator-schedules"),
    path("schedules/<int:user_id>/", ScheduleView.as_view(), name="coordinator-schedule"),
]
