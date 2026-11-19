from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .invitations import InvitationLookupView
from .password_reset import PasswordResetConfirmView, PasswordResetRequestView
from .views import LoginView, MeView, SignupView, TablePreferenceDetailView, TablePreferenceListView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="auth-signup"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("invitations/<str:token>/", InvitationLookupView.as_view(), name="auth-invitation"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/table-preferences/", TablePreferenceListView.as_view(), name="table-preferences"),
    path(
        "me/table-preferences/<slug:table_id>/", TablePreferenceDetailView.as_view(), name="table-preference-detail"
    ),
]
