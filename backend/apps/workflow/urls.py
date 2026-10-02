from django.urls import path

from .views import BoardColumnView, BoardConfigView, BoardStatusDetailView, WorkflowTransitionDetailView

urlpatterns = [
    path("boards/<int:pk>/config/", BoardConfigView.as_view(), name="board-config"),
    path("boards/<int:pk>/columns/<int:index>/", BoardColumnView.as_view(), name="board-column"),
    path("boards/<int:pk>/statuses/<int:status_id>/", BoardStatusDetailView.as_view(), name="board-status-detail"),
    path("workflow-transitions/<int:pk>/", WorkflowTransitionDetailView.as_view(), name="workflow-transition-detail"),
]
