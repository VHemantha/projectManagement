from django.urls import path

from .todos import TodoDetailView, TodoListView, clear_done

urlpatterns = [
    path("", TodoListView.as_view(), name="todo-list"),
    path("clear-done/", clear_done, name="todo-clear-done"),
    path("<int:pk>/", TodoDetailView.as_view(), name="todo-detail"),
]
