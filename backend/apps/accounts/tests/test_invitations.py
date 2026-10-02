"""Sign-up by invitation: admins invite, the link works once and expires, role/team applied."""
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.invitations import hash_token
from apps.accounts.models import Invitation, User
from apps.orgs.models import Organization
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return User.objects.create_user(username="boss", email="boss@example.com", password="x", is_staff=True, display_name="Boss")


@pytest.fixture
def admin_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def team():
    return Team.objects.create(organization=Organization.get_solo(), name="Payroll")


def token_from(url):
    return re.search(r"invite=([\w-]+)", url).group(1)


def send(admin_client, email="new@example.com", **extra):
    resp = admin_client.post("/api/invitations/", {"email": email, **extra}, format="json", HTTP_ORIGIN="https://app.example.com")
    assert resp.status_code == 201, resp.data
    return resp.data


def signup(token, username="newbie", **extra):
    return APIClient().post(
        "/api/auth/signup/",
        {"username": username, "password": "a-strong-pw-1", "display_name": "New Person", "invite_token": token, **extra},
        format="json",
    )


def test_admin_invites_and_the_email_carries_a_single_use_link(admin_client, team):
    data = send(admin_client, "New@Example.com", role="worker", team_id=team.id)
    assert data["email"] == "new@example.com"
    assert data["status"] == "pending"
    assert data["email_sent"] is True
    assert data["invite_url"].startswith("https://app.example.com/signup?invite=")
    assert len(mail.outbox) == 1
    assert data["invite_url"] in mail.outbox[0].body
    assert mail.outbox[0].to == ["new@example.com"]

    token = token_from(data["invite_url"])
    invitation = Invitation.objects.get()
    assert invitation.token_hash == hash_token(token) and token not in invitation.token_hash  # only the hash is stored
    assert invitation.expires_at - invitation.sent_at == timedelta(days=7)

    lookup = APIClient().get(f"/api/auth/invitations/{token}/").data
    assert lookup["email"] == "new@example.com" and lookup["team_name"] == "Payroll"

    # The email is locked to the invitation's, whatever the form sends.
    resp = signup(token, email="someone-else@example.com")
    assert resp.status_code == 201, resp.data
    user = User.objects.get(username="newbie")
    assert user.email == "new@example.com" and not user.is_staff
    assert TeamMembership.objects.filter(team=team, user=user).exists()
    assert Invitation.objects.get().status_at(timezone.now()) == "accepted"

    again = signup(token, username="twice")
    assert again.status_code == 410
    assert "already been used" in again.data["detail"]


def test_admin_role_makes_an_organisation_admin(admin_client):
    token = token_from(send(admin_client, role="admin")["invite_url"])
    assert signup(token).status_code == 201
    assert User.objects.get(username="newbie").is_staff


def test_expired_revoked_and_replaced_links_stop_working(admin_client):
    data = send(admin_client)
    old = token_from(data["invite_url"])
    resent = admin_client.post(f"/api/invitations/{data['id']}/resend/", HTTP_ORIGIN="https://app.example.com").data
    new = token_from(resent["invite_url"])
    assert new != old and len(mail.outbox) == 2
    assert signup(old).status_code == 410  # replaced by the resend

    Invitation.objects.filter(pk=data["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    resp = signup(new)
    assert resp.status_code == 410 and "expired" in resp.data["detail"]

    # Resending revives an expired invitation; revoking kills it.
    newer = token_from(admin_client.post(f"/api/invitations/{data['id']}/resend/").data["invite_url"])
    assert admin_client.post(f"/api/invitations/{data['id']}/revoke/").data["status"] == "revoked"
    resp = signup(newer)
    assert resp.status_code == 410 and "withdrawn" in resp.data["detail"]
    assert admin_client.post(f"/api/invitations/{data['id']}/resend/").status_code == 400


def test_invite_validation(admin_client, admin):
    assert admin_client.post("/api/invitations/", {"email": admin.email}, format="json").status_code == 400
    send(admin_client, "dup@example.com")
    resp = admin_client.post("/api/invitations/", {"email": "DUP@example.com"}, format="json")
    assert resp.status_code == 400 and "pending invitation" in str(resp.data["email"][0])


def test_only_admins_manage_invitations(admin_client):
    worker = User.objects.create_user(username="w", email="w@example.com", password="x")
    client = APIClient()
    client.force_authenticate(user=worker)
    assert client.get("/api/invitations/").status_code == 403
    assert client.post("/api/invitations/", {"email": "x@example.com"}, format="json").status_code == 403
    data = send(admin_client)
    assert client.post(f"/api/invitations/{data['id']}/revoke/").status_code == 403
    assert APIClient().get("/api/invitations/").status_code == 401
    listed = admin_client.get("/api/invitations/").data
    assert [i["email"] for i in listed] == ["new@example.com"]
    assert "invite_url" not in listed[0]  # links are only shown when sent


def test_unknown_token(admin_client):
    resp = APIClient().get("/api/auth/invitations/not-a-real-token/")
    assert resp.status_code == 410
    assert signup("not-a-real-token").status_code == 410


def test_a_failed_email_still_returns_the_link(admin_client, settings, monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("SMTP down")

    monkeypatch.setattr("apps.accounts.invitations.send_mail", boom)
    data = send(admin_client)
    assert data["email_sent"] is False
    assert "invite=" in data["invite_url"]
