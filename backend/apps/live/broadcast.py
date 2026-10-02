"""Live updates: tell every open TrackFlow tab that some data changed, so boards, lists and
open issues refetch it (frontend: src/api/useLiveUpdates.ts).

Events are tiny "what changed" notices, never data, e.g. {"kind": "issues", "project": "TRK",
"key": "TRK-12"}. Clients re-read through the normal REST API, so permissions and serializers
stay in one place and a missed event is repaired by the next fetch. Events go out only after
the database transaction commits, so a client never refetches before the change is visible.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

LIVE_GROUP = "live_updates"

# What each kind invalidates on the client:
#   issues   -> issue lists/boards + that issue          (Issue saved/deleted, labels changed)
#   issue    -> one issue's detail (comments, links, attachments)
#   board    -> a project's board config, statuses, transition rules
#   project  -> project details, labels, the Projects tree
#   sprints  -> a project's sprints (and issue lists, since sprint moves bypass Issue.save)
#   teams / clients -> team and client lists, the Projects tree
KINDS = {"issues", "issue", "board", "project", "sprints", "teams", "clients"}


def notify(kind: str, project: str | None = None, key: str | None = None) -> None:
    """Queue a change notice for after the current transaction commits (immediately when not
    inside one). Never raises: live updates are best-effort and must not break a request."""
    if kind not in KINDS:
        raise ValueError(f"Unknown live update kind: {kind}")
    event = {"type": "live.change", "kind": kind, "project": project, "key": key}
    transaction.on_commit(lambda: _send(event))


def user_group(user_id: int) -> str:
    """Each signed-in user's own group: their open tabs join it for personal events."""
    return f"user_{user_id}"


def push_to_user(user_id: int, payload: dict) -> None:
    """Send one person a personal event (a desktop-notification candidate: new DM, @mention,
    bell notification) after the transaction commits. Unlike change notices this carries the
    text to show, because it is only ever sent to its recipient."""
    event = {"type": "inbox.event", "event": payload}
    transaction.on_commit(lambda: _send(event, user_group(user_id)))


def _send(event: dict, group: str = LIVE_GROUP) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, event)
    except Exception:  # e.g. Redis briefly unavailable
        logger.warning("Live update broadcast failed: %s", event, exc_info=True)
