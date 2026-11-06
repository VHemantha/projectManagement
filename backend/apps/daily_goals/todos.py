"""The to-do list on the dashboard (AFIT, 5 Nov 2026): each person's own list of work and personal
things, apart from the morning plan. Only its owner can see or change it.

GET  /api/todos/            your list (open first, then done; ?done=0 for open only)
POST /api/todos/            {text, kind?, due_date?}
PATCH/DELETE /api/todos/<id>/
POST /api/todos/clear-done/ remove everything you have ticked
"""
from django.utils import timezone
from rest_framework import generics, permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import TodoItem

DONE_SHOWN = 30  # the most recent ticked items kept in the list


class TodoSerializer(serializers.ModelSerializer):
    text = serializers.CharField(max_length=300, trim_whitespace=True)

    class Meta:
        model = TodoItem
        fields = ["id", "text", "kind", "due_date", "done", "done_at", "created_at"]
        read_only_fields = ["done_at", "created_at"]

    def update(self, instance, validated_data):
        if "done" in validated_data and validated_data["done"] != instance.done:
            instance.done_at = timezone.now() if validated_data["done"] else None
        return super().update(instance, validated_data)


class TodoListView(generics.ListCreateAPIView):
    serializer_class = TodoSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        mine = TodoItem.objects.filter(user=self.request.user)
        if self.request.query_params.get("done") == "0":
            return mine.filter(done=False)
        done_ids = list(mine.filter(done=True).order_by("-done_at", "-id").values_list("id", flat=True)[:DONE_SHOWN])
        return mine.filter(done=False) | mine.filter(id__in=done_ids)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TodoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TodoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TodoItem.objects.filter(user=self.request.user)  # someone else's item: 404


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def clear_done(request):
    removed, _ = TodoItem.objects.filter(user=request.user, done=True).delete()
    return Response({"removed": removed})
