"""Password reset by email (18 Nov 2026): the link works once, the request never says who has an account."""
import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fresh_throttle():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def sandani():
    return User.objects.create_user(username="sandani", email="sandani.t@example.com", password="old-pw-123", display_name="Sandani")


def link(body):
    m = re.search(r"/reset-password\?uid=([\w-]+)&token=([\w-]+)", body)
    return m.group(1), m.group(2)


def confirm(uid, token, password="a-new-strong-pw-7"):
    return APIClient().post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": password}, format="json")


def test_a_reset_link_is_emailed_and_sets_the_password_once(sandani):
    resp = APIClient().post("/api/auth/password-reset/", {"email": "Sandani.T@example.com"}, format="json", HTTP_ORIGIN="https://app.example.com")
    assert resp.status_code == 200 and len(mail.outbox) == 1 and mail.outbox[0].to == ["sandani.t@example.com"]
    assert "https://app.example.com/reset-password?uid=" in mail.outbox[0].body
    uid, token = link(mail.outbox[0].body)
    assert confirm(uid, token, "short").status_code == 400  # the password rules apply
    resp = confirm(uid, token)
    assert resp.status_code == 200 and resp.data["email"] == "sandani.t@example.com"
    sandani.refresh_from_db()
    assert sandani.check_password("a-new-strong-pw-7")
    assert confirm(uid, token, "another-strong-pw-9").status_code == 410  # used up
    login = APIClient().post("/api/auth/login/", {"email": "sandani.t@example.com", "password": "a-new-strong-pw-7"}, format="json")
    assert login.status_code == 200


def test_the_request_never_says_whether_an_account_exists(sandani):
    known = APIClient().post("/api/auth/password-reset/", {"email": "sandani.t@example.com"}, format="json")
    unknown = APIClient().post("/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json")
    assert known.status_code == unknown.status_code == 200 and known.data == unknown.data
    assert len(mail.outbox) == 1
    sandani.is_active = False
    sandani.save()
    APIClient().post("/api/auth/password-reset/", {"email": "sandani.t@example.com"}, format="json")
    assert len(mail.outbox) == 1  # an inactive account gets nothing


def test_a_bad_link_is_refused(sandani):
    assert confirm("MQ", "not-a-token").status_code == 410
    assert confirm("!!", "x").status_code == 410


def test_an_admin_sends_the_link_from_the_command_line(sandani):
    call_command("send_password_reset", "SANDANI.T@example.com")
    assert len(mail.outbox) == 1
    uid, token = link(mail.outbox[0].body)
    assert confirm(uid, token).status_code == 200
    with pytest.raises(CommandError):
        call_command("send_password_reset", "nobody@example.com")
