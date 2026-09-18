import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def existing_user():
    user = User(username="jane", email="jane@example.com", display_name="Jane Doe")
    user.set_password("correct-horse-1")
    user.save()
    return user


def test_signup_creates_user_and_returns_tokens(api_client):
    resp = api_client.post(
        "/api/auth/signup/",
        {"email": "new@example.com", "username": "newperson", "password": "a-strong-pw-1"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["user"]["email"] == "new@example.com"
    assert "access" in resp.data["tokens"]
    assert "refresh" in resp.data["tokens"]
    assert User.objects.filter(email="new@example.com").exists()


def test_signup_rejects_duplicate_email(api_client, existing_user):
    resp = api_client.post(
        "/api/auth/signup/",
        {"email": existing_user.email, "username": "someoneelse", "password": "a-strong-pw-1"},
        format="json",
    )
    assert resp.status_code == 400


def test_login_with_correct_credentials_returns_tokens(api_client, existing_user):
    resp = api_client.post(
        "/api/auth/login/",
        {"email": existing_user.email, "password": "correct-horse-1"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["user"]["email"] == existing_user.email
    assert "access" in resp.data["tokens"]


def test_login_with_wrong_password_is_rejected(api_client, existing_user):
    resp = api_client.post(
        "/api/auth/login/",
        {"email": existing_user.email, "password": "wrong-password"},
        format="json",
    )
    assert resp.status_code == 401


def test_me_requires_authentication(api_client):
    resp = api_client.get("/api/auth/me/")
    assert resp.status_code == 401


def test_me_returns_current_user_when_authenticated(api_client, existing_user):
    api_client.force_authenticate(user=existing_user)
    resp = api_client.get("/api/auth/me/")
    assert resp.status_code == 200
    assert resp.data["email"] == existing_user.email


def test_me_patch_updates_profile_fields(api_client, existing_user):
    api_client.force_authenticate(user=existing_user)
    resp = api_client.patch(
        "/api/auth/me/", {"display_name": "Jane Updated", "job_title": "Staff Engineer"}, format="json"
    )
    assert resp.status_code == 200
    existing_user.refresh_from_db()
    assert existing_user.display_name == "Jane Updated"
    assert existing_user.job_title == "Staff Engineer"
