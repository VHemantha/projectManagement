from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, SignupView, TablePreferenceDetailView, TablePreferenceListView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="auth-signup"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/table-preferences/", TablePreferenceListView.as_view(), name="table-preferences"),
    path(
        "me/table-preferences/<slug:table_id>/", TablePreferenceDetailView.as_view(), name="table-preference-detail"
    ),
]
