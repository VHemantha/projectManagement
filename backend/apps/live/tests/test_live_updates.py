from unittest import mock

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.db import transaction
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults


@pytest.fixture
def lead(db):
    return User.objects.create_user(username="live_lead", email="live_lead@example.com", password="x")


@pytest.fixture
def api_client(lead):
    client = APIClient()
    client.force_authenticate(user=lead)
    return client


@pytest.fixture
def project(lead):
    project = Project.objects.create(organization=Organization.get_solo(), key="LIV", name="Live", lead=lead)
    provision_project_defaults(project)
    return project


@pytest.fixture
def sent():
    """Every event broadcast.notify() actually sends (i.e. after commit)."""
    with mock.patch("apps.live.broadcast._send") as send:
        yield send


def _events(send_mock):
    return [(c.args[0]["kind"], c.args[0]["project"], c.args[0]["key"]) for c in send_mock.call_args_list]


def _task():
    return IssueType.objects.get_or_create(name="Task", project=None)[0]


def test_moving_an_issue_broadcasts_after_commit(api_client, project, sent, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post("/api/issues/", {"project": "LIV", "summary": "Live", "issue_type_id": _task().id}, format="json")
    key = resp.data["key"]
    in_progress = project.workflow.statuses.get(name="In Progress")
    sent.reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        api_client.post(f"/api/issues/{key}/move/", {"status_id": in_progress.id}, format="json")
    assert ("issues", "LIV", key) in _events(sent)


def test_nothing_is_sent_before_commit_or_on_rollback(api_client, project, sent, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                Issue.objects.create(
                    project=project, key="LIV-99", summary="x", issue_type=_task(), reporter=project.lead,
                    status=project.workflow.statuses.first(), rank="000001",
                )
                assert sent.call_count == 0  # not before commit
                raise RuntimeError("roll back")
    assert sent.call_count == 0


def test_board_config_change_broadcasts_board(api_client, project, sent, django_capture_on_commit_callbacks):
    board = project.boards.first()
    with django_capture_on_commit_callbacks(execute=True):
        api_client.patch(f"/api/boards/{board.id}/config/", {"card_color_rule": "priority"}, format="json")
    assert ("board", "LIV", None) in _events(sent)


def test_reviewer_reassign_rule_change_broadcasts_board(api_client, project, sent, django_capture_on_commit_callbacks):
    transition = project.workflow.transitions.first()
    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.patch(
            f"/api/workflow-transitions/{transition.id}/", {"set_current_responsible_to": "reviewer"}, format="json"
        )
    assert resp.status_code == 200
    assert ("board", "LIV", None) in _events(sent)


def test_sprint_reorder_broadcasts_despite_bulk_update(api_client, project, sent, django_capture_on_commit_callbacks):
    from apps.sprints.models import Sprint

    a = Sprint.objects.create(project=project, name="A", order=0)
    b = Sprint.objects.create(project=project, name="B", order=1)
    sent.reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        api_client.post("/api/projects/LIV/sprints/reorder/", {"order": [b.id, a.id]}, format="json")
    assert ("sprints", "LIV", None) in _events(sent)


def test_broadcast_failure_never_breaks_the_request(api_client, project, django_capture_on_commit_callbacks):
    layer = mock.Mock()
    layer.group_send = mock.AsyncMock(side_effect=ConnectionError("redis down"))
    with mock.patch("apps.live.broadcast.get_channel_layer", return_value=layer):
        with django_capture_on_commit_callbacks(execute=True):
            resp = api_client.post(
                "/api/issues/", {"project": "LIV", "summary": "Still saved", "issue_type_id": _task().id}, format="json"
            )
    assert resp.status_code == 201
    assert layer.group_send.await_count >= 1


# --- The socket ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_socket_rejects_anonymous_users():
    from trackflow.asgi import application

    communicator = WebsocketCommunicator(application, "/ws/live/")
    connected, _ = await communicator.connect()
    assert not connected


@pytest.mark.django_db(transaction=True)
async def test_socket_relays_change_notices():
    from channels.db import database_sync_to_async

    from apps.live.broadcast import LIVE_GROUP
    from trackflow.asgi import application

    user = await database_sync_to_async(User.objects.create_user)(
        username="live_viewer", email="live_viewer@example.com", password="x"
    )
    token = str(RefreshToken.for_user(user).access_token)
    communicator = WebsocketCommunicator(application, f"/ws/live/?token={token}")
    connected, _ = await communicator.connect()
    assert connected

    await get_channel_layer().group_send(
        LIVE_GROUP, {"type": "live.change", "kind": "board", "project": "LIV", "key": None}
    )
    assert await communicator.receive_json_from(timeout=2) == {
        "type": "live.change", "kind": "board", "project": "LIV", "key": None,
    }
    await communicator.disconnect()
