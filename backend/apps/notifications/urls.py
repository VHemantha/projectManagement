from django.urls import path

from .views import NotificationListView, NotificationMarkReadView, mark_all_read, unread_count

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", unread_count, name="notification-unread-count"),
    path("mark-all-read/", mark_all_read, name="notification-mark-all-read"),
    path("<int:pk>/read/", NotificationMarkReadView.as_view(), name="notification-mark-read"),
]
