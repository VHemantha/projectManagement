import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.chat.models import Channel
from apps.orgs.models import Organization
from apps.projects.models import Project, ProjectMembership
from trackflow.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


def _token_for(user):
    return str(RefreshToken.for_user(user).access_token)


async def test_member_can_connect_send_and_receive_message():
    lead = await _make_project_lead()
    channel = await _project_channel(lead)
    token = _token_for(lead)

    communicator = WebsocketCommunicator(application, f"/ws/chat/{channel.id}/?token={token}")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to(
        {"type": "message.send", "body": {"type": "doc", "content": [{"type": "paragraph"}]}}
    )
    response = await communicator.receive_json_from(timeout=5)
    assert response["type"] == "message.new"
    assert response["message"]["author"]["id"] == lead.id

    await communicator.disconnect()


async def test_non_member_connection_is_rejected():
    lead = await _make_project_lead()
    channel = await _project_channel(lead)

    outsider = await _make_user("outsider", "outsider@example.com")
    token = _token_for(outsider)

    communicator = WebsocketCommunicator(application, f"/ws/chat/{channel.id}/?token={token}")
    connected, _ = await communicator.connect()
    assert not connected


async def test_connection_without_token_is_rejected():
    lead = await _make_project_lead()
    channel = await _project_channel(lead)

    communicator = WebsocketCommunicator(application, f"/ws/chat/{channel.id}/")
    connected, _ = await communicator.connect()
    assert not connected


async def test_two_members_both_receive_a_broadcast_message():
    lead = await _make_project_lead()
    channel = await _project_channel(lead)
    member = await _add_project_member(channel, "member1", "member1@example.com")

    comm_a = WebsocketCommunicator(application, f"/ws/chat/{channel.id}/?token={_token_for(lead)}")
    comm_b = WebsocketCommunicator(application, f"/ws/chat/{channel.id}/?token={_token_for(member)}")
    assert (await comm_a.connect())[0]
    assert (await comm_b.connect())[0]

    await comm_a.send_json_to({"type": "message.send", "body": {"type": "doc", "content": []}})

    msg_a = await comm_a.receive_json_from(timeout=5)
    msg_b = await comm_b.receive_json_from(timeout=5)
    assert msg_a["message"]["id"] == msg_b["message"]["id"]

    await comm_a.disconnect()
    await comm_b.disconnect()


# -- async DB helpers ---------------------------------------------------------


@database_sync_to_async
def _make_user(username, email):
    return User.objects.create_user(username=username, email=email, password="x")


@database_sync_to_async
def _make_project_lead():
    org = Organization.get_solo()
    lead = User.objects.create_user(username="ws_lead", email="ws_lead@example.com", password="x")
    project = Project.objects.create(organization=org, key="WSK", name="WS Test", lead=lead)
    ProjectMembership.objects.create(project=project, user=lead, role="admin")
    return lead


@database_sync_to_async
def _project_channel(lead):
    project = Project.objects.get(lead=lead)
    return Channel.objects.get(linked_project=project)


@database_sync_to_async
def _add_project_member(channel, username, email):
    user = User.objects.create_user(username=username, email=email, password="x")
    ProjectMembership.objects.create(project=channel.linked_project, user=user, role="member")
    return user
