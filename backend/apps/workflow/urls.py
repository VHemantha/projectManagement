from django.urls import path

from .views import BoardConfigView, BoardStatusDetailView, WorkflowTransitionDetailView

urlpatterns = [
    path("boards/<int:pk>/config/", BoardConfigView.as_view(), name="board-config"),
    path("boards/<int:pk>/statuses/<int:status_id>/", BoardStatusDetailView.as_view(), name="board-status-detail"),
    path("workflow-transitions/<int:pk>/", WorkflowTransitionDetailView.as_view(), name="workflow-transition-detail"),
]
