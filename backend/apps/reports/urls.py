from django.urls import path

from .ceo import CeoDashboardView, CeoExcelReportView
from .people import PeopleSnapshotView, PersonDashboardView
from .views import BudgetVsActualView, NavTreeView, PersonKpiView

urlpatterns = [
    path("nav-tree/", NavTreeView.as_view(), name="nav-tree"),
    path("budget-vs-actual/", BudgetVsActualView.as_view(), name="budget-vs-actual"),
    path("people/", PeopleSnapshotView.as_view(), name="people-snapshot"),
    path("people/<int:pk>/", PersonDashboardView.as_view(), name="person-dashboard"),
    path("people/<int:user_id>/kpi/", PersonKpiView.as_view(), name="person-kpi"),
    path("ceo-dashboard/", CeoDashboardView.as_view(), name="ceo-dashboard"),
    path("ceo-report.xlsx", CeoExcelReportView.as_view(), name="ceo-report"),
]
