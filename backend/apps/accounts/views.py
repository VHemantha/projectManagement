import json

from django.contrib.auth import authenticate
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import TablePreference, User
from .serializers import LoginSerializer, SignupSerializer, UserSerializer


def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class SignupView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = SignupSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"user": UserSerializer(user).data, "tokens": _tokens_for(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"user": UserSerializer(user).data, "tokens": _tokens_for(user)})


class UserListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    queryset = User.objects.filter(is_active=True).order_by("display_name")
    filter_backends = []
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(display_name__icontains=q)
        return qs


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        return self.request.user


class TablePreferenceListView(APIView):
    """GET /api/auth/me/table-preferences/ — {table_id: state} for every table the current
    user has customised."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({p.table_id: p.state for p in TablePreference.objects.filter(user=request.user)})


class TablePreferenceDetailView(APIView):
    """PUT saves the current user's layout for one table; DELETE resets it to the default."""

    permission_classes = [permissions.IsAuthenticated]
    MAX_STATE_BYTES = 20_000

    def put(self, request, table_id):
        state = request.data.get("state")
        if not isinstance(state, dict):
            return Response({"detail": "state must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        if len(json.dumps(state)) > self.MAX_STATE_BYTES:
            return Response({"detail": "Table layout is too large."}, status=status.HTTP_400_BAD_REQUEST)
        TablePreference.objects.update_or_create(user=request.user, table_id=table_id, defaults={"state": state})
        return Response({"table_id": table_id, "state": state})

    def delete(self, request, table_id):
        TablePreference.objects.filter(user=request.user, table_id=table_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
