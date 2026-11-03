"""What passed between the agent and the accountant on each follow-up, for the CEO (AFIT, 2 Nov 2026):
the messages the agent sent to the accountant in their private conversation (with the next steps it
suggested), the reasons they gave in reply, the agent's guidance back, and any escalation to the
team lead. Read from the agent's own records; nothing here is new or the AI's own arithmetic."""
from .models import AgentAction, AgentCase

TEXT_LIMIT = 1500


def _text(action: AgentAction) -> str:
    from .conversation import _text_of

    if action.detail.get("text"):
        return action.detail["text"]
    if action.message_id:
        return _text_of(action.message.body)
    return action.reason  # an older shadow-mode record keeps only why it would have been sent


def _guidance(reply: AgentAction | None) -> str:
    """The agent's answer to a reason, without the figures code adds after it."""
    if reply is None or not reply.message_id:
        return ""
    from .conversation import _text_of

    paragraphs = [p for p in _paragraphs(reply.message.body) if not p.startswith("Noted for ") and p != "I've let the team lead know."]
    return " ".join(paragraphs).strip() or _text_of(reply.message.body)


def _paragraphs(body) -> list[str]:
    from .conversation import _text_of

    return [_text_of(p) for p in (body or {}).get("content", []) if _text_of(p)]


def replies_after(people_ids, since):
    """The agent's replies to these people, oldest first."""
    return list(AgentAction.objects.filter(trigger="reply", target_id__in=people_ids, created_at__gte=since)
                .select_related("message").order_by("created_at", "id"))


def reply_to_commitment(commitment, replies: list[AgentAction]) -> AgentAction | None:
    """The agent's reply to the message the commitment was read from (written straight after it)."""
    return next((r for r in replies if r.target_id == commitment.person_id and r.created_at >= commitment.created_at), None)


def guidance_for(commitment, replies: list[AgentAction]) -> str:
    return _guidance(reply_to_commitment(commitment, replies))[:TEXT_LIMIT]


def histories(cases: list[AgentCase]) -> dict[int, list[dict]]:
    """{case id: the exchange, oldest first}."""
    from .conversation import _text_of

    if not cases:
        return {}
    since = min(c.opened_at for c in cases)
    kinds = {c.kind for c in cases} | {"escalation"}
    actions = list(AgentAction.objects.filter(issue_id__in={c.issue_id for c in cases}, trigger__in=kinds, created_at__gte=since)
                   .select_related("message", "target").order_by("created_at", "id"))
    replies = replies_after({c.person_id for c in cases}, since)
    out = {}
    for c in cases:
        rows = []
        for a in actions:
            if a.issue_id != c.issue_id or a.created_at < c.opened_at or (c.closed_at and a.created_at > c.closed_at):
                continue
            if a.trigger == c.kind and a.target_id == c.person_id and a.detail.get("case", c.pk) == c.pk:
                rows.append({"at": a.created_at, "kind": "asked", "from": "agent", "to": a.target.display_name, "text": _text(a)[:TEXT_LIMIT],
                             "advice": a.detail.get("advice", []), "shadow": a.shadow, "delivered": a.message_id is not None})
            elif a.trigger == "escalation" and a.detail.get("case", c.pk) == c.pk and a.target_id == c.escalated_to_id:
                rows.append({"at": a.created_at, "kind": "escalated", "from": "agent", "to": a.target.display_name if a.target else "",
                             "text": _text(a)[:TEXT_LIMIT], "advice": [], "shadow": a.shadow, "delivered": a.message_id is not None})
        for m in c.commitments.all():
            words = _text_of(m.source_message.body) if m.source_message_id else ""
            rows.append({"at": m.created_at, "kind": "reason", "from": "person", "to": "", "text": words[:TEXT_LIMIT], "advice": [],
                         "cause": m.get_cause_display(), "blockers": m.blockers, "eta_date": m.eta_date, "remaining_hours": m.remaining_hours,
                         "needs_help": m.needs_help, "shadow": False, "delivered": True})
            reply = reply_to_commitment(m, replies)
            if reply is not None:
                rows.append({"at": reply.created_at, "kind": "guidance", "from": "agent", "to": c.person.display_name,
                             "text": _guidance(reply)[:TEXT_LIMIT], "advice": [], "shadow": False, "delivered": reply.message_id is not None})
        rows.sort(key=lambda r: r["at"])
        out[c.pk] = rows
    return out
