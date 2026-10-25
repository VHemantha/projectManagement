"""The CEO's daily briefing: once each working day, at the briefing time, a short note in the CEO's
conversation with the agent. Code gathers the facts (jobs overdue or due soon, open follow-ups,
escalations, dates missed); Sonnet writes a few sentences on top; the lists follow, exactly."""
import logging
from datetime import datetime

from . import calendar, llm, policies, services
from .facts import local_now, open_jobs, responsible
from .models import AgentAction, AgentCase, Commitment

logger = logging.getLogger(__name__)
TRIGGER = "ceo_briefing"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary"], "properties": {"summary": {"type": "string"}}}
SYSTEM = """You are the Loca Coordinator, the AI project coordinator at AFIT Connect, writing the CEO's morning briefing. From the facts given, write 2 to 4 short sentences: what most needs the CEO's attention today and why. Use only the facts given; never invent a job, a person, a figure or a cause. Do not assume anyone is at fault. No greeting, no sign-off; New Zealand English."""


def facts(today=None) -> dict:
    today = today or local_now().date()
    cases = list(AgentCase.objects.exclude(state=AgentCase.State.RESOLVED).select_related("issue__project__client", "person", "escalated_to"))
    overdue = [c for c in cases if c.kind in (AgentCase.Kind.PRECHECK_OVERDUE, AgentCase.Kind.PREP_OVERDUE)]
    due_soon = [c for c in cases if c.kind in (AgentCase.Kind.PRECHECK_DUE, AgentCase.Kind.PREP_DUE)]
    escalated = [c for c in cases if c.state == AgentCase.State.ESCALATED]
    missed = [c for c in cases if c.kind == AgentCase.Kind.PROMISE_MISSED]
    waiting = [c for c in cases if c.state == AgentCase.State.ASKED and c.asked > 0]
    jobs = list(open_jobs())
    return {"today": today, "open_jobs": len(jobs), "unassigned": sum(1 for j in jobs if responsible(j) is None),
            "overdue": overdue, "due_soon": due_soon, "escalated": escalated, "missed": missed, "waiting": waiting,
            "kept_yesterday": Commitment.objects.filter(status=Commitment.Status.KEPT, verified_at__date__gte=calendar.previous_working_day(today) or today).count()}


def _line(c: AgentCase) -> str:
    client = c.issue.project.client.name if c.issue.project.client_id else c.issue.project.name
    extra = f"; revised {c.revised_due:%d %b}" if c.revised_due else ""
    return f"{c.issue.key} {c.issue.summary[:60]} ({client}) — {c.person.display_name}; {c.get_kind_display().lower()}, due {c.due_date:%d %b}{extra}"


def compose(f: dict) -> tuple[str, float]:
    sections = [("Overdue", f["overdue"]), ("Due in the next days", f["due_soon"]), ("Escalated to a team lead", f["escalated"]),
                ("Revised dates missed", f["missed"]), ("Waiting for a reply", f["waiting"])]
    facts_text = "\n".join([f"Today: {f['today']:%A %d %B %Y}. Open jobs: {f['open_jobs']} ({f['unassigned']} with nobody responsible). "
                            f"Promises kept since the last working day: {f['kept_yesterday']}."]
                           + [f"{title} ({len(items)}): " + "; ".join(_line(c) for c in items[:15]) for title, items in sections if items])
    cost_usd = 0.0
    try:
        answer, cost_usd = llm.structured(SYSTEM, [{"role": "user", "content": facts_text}], SCHEMA, max_tokens=600)
        summary = str(answer.get("summary", "")).strip()
    except llm.Unavailable:
        summary = ""
    if not summary:
        n = len(f["overdue"])
        summary = (f"{n} stage{'s are' if n != 1 else ' is'} overdue and {len(f['due_soon'])} due soon." if n or f["due_soon"]
                   else "Nothing is overdue and nothing is due in the next days.")
    body = [f"Good morning. Your briefing for {f['today']:%A %d %B}.", summary]
    for title, items in sections:
        if items:
            body.append(f"{title} ({len(items)}):\n" + "\n".join(f"• {_line(c)}" for c in items[:15])
                        + (f"\n…and {len(items) - 15} more" if len(items) > 15 else ""))
    if f["unassigned"]:
        body.append(f"{f['unassigned']} open job{'s have' if f['unassigned'] != 1 else ' has'} nobody responsible, so I can't follow them up.")
    return "\n\n".join(body), cost_usd


def send_if_due(now: datetime) -> bool:
    """Send today's briefing if it is a working day, past the briefing time, and not yet sent."""
    ceo = services.ceo()
    t = local_now(now)
    if ceo is None or not calendar.is_working_day(t.date()) or t.strftime("%H:%M") < policies.resolve("ceo_briefing_time"):
        return False
    day = t.date().isoformat()
    if AgentAction.objects.filter(trigger=TRIGGER, detail__date=day).exists():  # one a day, keyed by its date
        return False
    text, cost_usd = compose(facts(t.date()))
    message = services.post_as_agent(services.conversation_for(ceo), text)
    AgentAction.objects.create(trigger=TRIGGER, target=ceo, reason="Daily briefing for the CEO", message=message, cost_usd=cost_usd,
                               detail={"date": day})
    return True
