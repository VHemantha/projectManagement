from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .inbox import recent_events
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related(
            "actor", "target_issue", "target_issue__project", "target_message", "target_message__channel"
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def inbox_events(request):
    """GET /api/notifications/inbox/?since=<ISO time> — the polling fallback for desktop
    notifications when the live socket is down. Returns events after `since` (default: the last
    two minutes) and `now`, the cursor for the next poll."""
    now = timezone.now()
    since = parse_datetime(request.query_params.get("since") or "")
    if since is None:
        since = now - timedelta(minutes=2)
    elif timezone.is_naive(since):
        since = timezone.make_aware(since)
    since = max(since, now - timedelta(days=1))  # never replay old history
    events = recent_events(request.user, since) if request.user.desktop_notifications else []
    return Response({"events": events, "now": now.isoformat()})


class NotificationMarkReadView(generics.UpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"detail": "ok"})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def unread_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response({"count": count})
