from django.urls import path

from .views import DailyGoalDetailView, DailyGoalListCreateView, carry_over_goal

urlpatterns = [
    path("", DailyGoalListCreateView.as_view(), name="daily-goal-list"),
    path("<int:pk>/", DailyGoalDetailView.as_view(), name="daily-goal-detail"),
    path("<int:pk>/carry-over/", carry_over_goal, name="daily-goal-carry-over"),
]
