from rest_framework import generics, permissions

from .models import Client
from .serializers import ClientSerializer


class ClientListCreateView(generics.ListCreateAPIView):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    queryset = Client.objects.all()

    def perform_create(self, serializer):
        from apps.orgs.models import Organization

        serializer.save(organization=Organization.get_solo())


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Client.objects.all()
