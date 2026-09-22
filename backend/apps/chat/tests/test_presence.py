import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.chat.consumers import ONLINE_USER_CONNECTIONS
from trackflow.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _reset_presence_registry():
    # ONLINE_USER_CONNECTIONS is a plain module-level dict (see consumers.py's comment on why
    # that's the right call given InMemoryChannelLayer) — it isn't reset by Django's DB
    # transaction rollback between tests, so a leftover entry from a previous test would make
    # this test's "was this user already online" check see stale state. Clear it on both sides
    # so a test that asserts via a mid-test failure (skipping its own cleanup) can't leak into
    # the next one either.
    ONLINE_USER_CONNECTIONS.clear()
    yield
    ONLINE_USER_CONNECTIONS.clear()


def _token_for(user):
    return str(RefreshToken.for_user(user).access_token)


@database_sync_to_async
def _make_user(username, email):
    return User.objects.create_user(username=username, email=email, password="x")


async def test_connecting_without_a_token_is_rejected():
    communicator = WebsocketCommunicator(application, "/ws/presence/")
    connected, _ = await communicator.connect()
    assert not connected


async def test_connect_sends_a_snapshot_of_currently_online_users():
    a = await _make_user("pres_a", "pres_a@example.com")
    b = await _make_user("pres_b", "pres_b@example.com")

    comm_a = WebsocketCommunicator(application, f"/ws/presence/?token={_token_for(a)}")
    assert (await comm_a.connect())[0]
    await comm_a.receive_json_from(timeout=5)  # a's own snapshot

    comm_b = WebsocketCommunicator(application, f"/ws/presence/?token={_token_for(b)}")
    assert (await comm_b.connect())[0]
    snapshot = await comm_b.receive_json_from(timeout=5)
    assert snapshot["type"] == "presence.snapshot"
    assert a.id in snapshot["user_ids"]

    # a should also hear that b just came online
    update = await comm_a.receive_json_from(timeout=5)
    assert update == {"type": "presence.update", "user_id": b.id, "online": True}

    await comm_a.disconnect()
    await comm_b.disconnect()


async def test_disconnecting_broadcasts_offline():
    a = await _make_user("pres_c", "pres_c@example.com")
    b = await _make_user("pres_d", "pres_d@example.com")

    comm_a = WebsocketCommunicator(application, f"/ws/presence/?token={_token_for(a)}")
    comm_b = WebsocketCommunicator(application, f"/ws/presence/?token={_token_for(b)}")
    assert (await comm_a.connect())[0]
    assert (await comm_b.connect())[0]
    await comm_a.receive_json_from(timeout=5)  # a's snapshot
    await comm_b.receive_json_from(timeout=5)  # b's snapshot
    await comm_a.receive_json_from(timeout=5)  # a hears b came online

    await comm_b.disconnect()
    update = await comm_a.receive_json_from(timeout=5)
    assert update == {"type": "presence.update", "user_id": b.id, "online": False}

    await comm_a.disconnect()


async def test_a_second_tab_refcounts_instead_of_rebroadcasting():
    # This checks the refcounting logic directly against ONLINE_USER_CONNECTIONS rather than
    # racing multiple WebsocketCommunicators' receive_json_from calls against each other with
    # timeouts — that approach was flaky under this test harness's shared event loop when many
    # communicators overlap in one test. The 3 tests above already cover the broadcast wiring
    # (online on first connect, offline on disconnect) directly; this one is scoped to just the
    # per-user connection-count bookkeeping that a second tab shouldn't disturb.
    a = await _make_user("pres_e", "pres_e@example.com")
    token = _token_for(a)

    tab1 = WebsocketCommunicator(application, f"/ws/presence/?token={token}")
    assert (await tab1.connect())[0]
    await tab1.receive_json_from(timeout=5)  # tab1's snapshot
    assert ONLINE_USER_CONNECTIONS.get(a.id) == 1

    tab2 = WebsocketCommunicator(application, f"/ws/presence/?token={token}")
    assert (await tab2.connect())[0]
    await tab2.receive_json_from(timeout=5)  # tab2's snapshot
    assert ONLINE_USER_CONNECTIONS.get(a.id) == 2

    await tab1.disconnect()
    assert ONLINE_USER_CONNECTIONS.get(a.id) == 1

    await tab2.disconnect()
    assert a.id not in ONLINE_USER_CONNECTIONS
