import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice():
    return User.objects.create_user(username="dm_alice", email="dm_alice@example.com", password="x")


@pytest.fixture
def bob():
    return User.objects.create_user(username="dm_bob", email="dm_bob@example.com", password="x")


@pytest.fixture
def carol():
    return User.objects.create_user(username="dm_carol", email="dm_carol@example.com", password="x")


@pytest.fixture
def outsider():
    return User.objects.create_user(username="dm_outsider", email="dm_outsider@example.com", password="x")


@pytest.fixture
def alice_client(alice):
    client = APIClient()
    client.force_authenticate(user=alice)
    return client


def test_creating_a_dm_with_one_other_user_makes_a_direct_message_channel(alice, alice_client, bob):
    resp = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    assert resp.status_code == 201
    assert resp.data["channel_type"] == "direct_message"
    participant_ids = {p["id"] for p in resp.data["participants"]}
    assert participant_ids == {alice.id, bob.id}
    channel = Channel.objects.get(id=resp.data["id"])
    assert set(channel.memberships.values_list("user_id", flat=True)) == {alice.id, bob.id}


def test_creating_a_dm_with_two_other_users_makes_a_group_dm(alice_client, bob, carol):
    resp = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id, carol.id]}, format="json")
    assert resp.status_code == 201
    assert resp.data["channel_type"] == "group_dm"


def test_requesting_the_same_dm_twice_returns_the_same_channel(alice_client, bob):
    r1 = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    r2 = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.data["id"] == r2.data["id"]
    assert Channel.objects.filter(channel_type="direct_message").count() == 1


def test_participant_order_does_not_create_a_duplicate_group_dm(alice_client, bob, carol):
    r1 = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id, carol.id]}, format="json")
    r2 = alice_client.post("/api/chat/dm/", {"participant_ids": [carol.id, bob.id]}, format="json")
    assert r1.data["id"] == r2.data["id"]


def test_a_dm_with_a_different_third_person_is_a_separate_channel(alice_client, bob, carol):
    r1 = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    r2 = alice_client.post("/api/chat/dm/", {"participant_ids": [carol.id]}, format="json")
    assert r1.data["id"] != r2.data["id"]


def test_dm_requires_at_least_one_other_participant(alice_client):
    resp = alice_client.post("/api/chat/dm/", {"participant_ids": []}, format="json")
    assert resp.status_code == 400


def test_non_participant_cannot_access_the_dm_channel(alice_client, bob, outsider):
    created = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    channel_id = created.data["id"]

    outsider_client = APIClient()
    outsider_client.force_authenticate(user=outsider)
    resp = outsider_client.get(f"/api/chat/channels/{channel_id}/")
    assert resp.status_code == 403


def test_dm_channel_does_not_appear_in_general_channel_list_filters_incorrectly(alice_client, bob):
    resp = alice_client.post("/api/chat/dm/", {"participant_ids": [bob.id]}, format="json")
    channel_id = resp.data["id"]
    listing = alice_client.get("/api/chat/channels/")
    assert any(c["id"] == channel_id for c in listing.data["results"])
