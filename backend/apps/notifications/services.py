from .models import Notification


def notify(user, verb, *, actor=None, target_issue=None, target_message=None):
    """Create a notification, skipping the no-op case of notifying someone about
    their own action."""
    if actor is not None and user_id_matches(user, actor):
        return None
    return Notification.objects.create(
        user=user, actor=actor, verb=verb, target_issue=target_issue, target_message=target_message
    )


def user_id_matches(user, actor):
    return getattr(user, "id", None) == getattr(actor, "id", None)


def notify_many(users, verb, *, actor=None, target_issue=None, target_message=None):
    seen = set()
    rows = []
    for user in users:
        if user is None or user.id in seen:
            continue
        if actor is not None and user_id_matches(user, actor):
            continue
        seen.add(user.id)
        rows.append(
            Notification(
                user=user, actor=actor, verb=verb, target_issue=target_issue, target_message=target_message
            )
        )
    if rows:
        Notification.objects.bulk_create(rows)
    return rows
