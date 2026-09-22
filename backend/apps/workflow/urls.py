from django.urls import path

from .views import BoardConfigView, WorkflowTransitionDetailView

urlpatterns = [
    path("boards/<int:pk>/config/", BoardConfigView.as_view(), name="board-config"),
    path("workflow-transitions/<int:pk>/", WorkflowTransitionDetailView.as_view(), name="workflow-transition-detail"),
]
