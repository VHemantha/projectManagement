from django.urls import path

from .views import DailyGoalDetailView, DailyGoalListCreateView, TeamPlansView, carry_over_goal, check_goal

urlpatterns = [
    path("", DailyGoalListCreateView.as_view(), name="daily-goal-list"),
    path("<int:pk>/", DailyGoalDetailView.as_view(), name="daily-goal-detail"),
    path("<int:pk>/carry-over/", carry_over_goal, name="daily-goal-carry-over"),
    path("<int:pk>/check/", check_goal, name="daily-goal-check"),
    path("team/", TeamPlansView.as_view(), name="daily-goal-team"),
]
