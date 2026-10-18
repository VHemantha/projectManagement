from django.urls import path

from .views import BudgetVsActualView, NavTreeView, PersonKpiView

urlpatterns = [
    path("nav-tree/", NavTreeView.as_view(), name="nav-tree"),
    path("budget-vs-actual/", BudgetVsActualView.as_view(), name="budget-vs-actual"),
    path("people/<int:user_id>/kpi/", PersonKpiView.as_view(), name="person-kpi"),
]
