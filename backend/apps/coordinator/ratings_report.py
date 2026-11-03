"""The CEO's weekly ratings report (AFIT, 31 Oct 2026): on the first working day of each week, after
the report time, the agent keeps everyone's ratings (kpi.snapshot) and sends the CEO, and only the
CEO, a note in their conversation with it: each person's rating and what changed since last week,
their weakest KPI, and the reasons given for delays. Code writes the lists; Sonnet adds a few
sentences on top, from those facts only."""
import logging
from datetime import datetime, timedelta

from . import calendar, kpi, llm, policies, services
from .facts import local_now
from .models import AgentAction

logger = logging.getLogger(__name__)
TRIGGER = "kpi_report"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary"], "properties": {"summary": {"type": "string"}}}
SYSTEM = """You are the TASKO Coordinator at AFIT Connect, writing the CEO's weekly note on the team's ratings. From the facts given, write 2 to 4 short sentences: who needs support and on what, what improved, and any pattern in the reasons given for delays. Use only the facts given; never invent a person, a figure or a cause. Be fair: a low score is something to look into, not a verdict. No greeting, no sign-off; New Zealand English."""


def _change(score, before) -> str:
    if score is None or before is None:
        return ""
    diff = round(score - before, 1)
    return " (no change)" if diff == 0 else f" ({'up' if diff > 0 else 'down'} {abs(diff):g} since last week)"


def _weakest(r: dict) -> str:
    counted = [m for m in r["metrics"] if m["counted"] and m["score"] is not None]
    if not counted:
        return ""
    m = min(counted, key=lambda m: m["score"])
    return f"; weakest: {m['label'].lower()} {m['score']:g} ({m['detail']})" if m["score"] < 85 else ""


def compose(rows: list[dict], before: dict, today) -> tuple[str, float]:
    lines = []
    for i, r in enumerate(rows, 1):
        score = "—" if r["score"] is None else f"{r['score']:g}"
        lines.append(f"{i}. {r['person']['display_name']} — {score}, {r['rating']}{_change(r['score'], before.get(r['person']['id']))}{_weakest(r)}")
    causes: dict[str, int] = {}
    for r in rows:
        for cause, n in r["reasons"].items():
            causes[cause] = causes.get(cause, 0) + n
    reasons = "; ".join(f"{c.lower()} {n}" for c, n in sorted(causes.items(), key=lambda x: -x[1])) or "none given"
    start, end = rows[0]["period"]["from"], rows[0]["period"]["to"]
    facts_text = (f"Period {start:%d %b} to {end:%d %b %Y}.\nRatings:\n" + "\n".join(lines)
                  + f"\nReasons given for delays in the period: {reasons}.")
    cost = 0.0
    try:
        answer, cost = llm.structured(SYSTEM, [{"role": "user", "content": facts_text}], SCHEMA, max_tokens=600)
        summary = str(answer.get("summary", "")).strip()
    except llm.Unavailable:
        summary = ""
    if not summary:
        risk = [r["person"]["display_name"] for r in rows if r["rating"] in ("At risk", "Needs improvement")]
        summary = (f"{', '.join(risk)} {'need' if len(risk) != 1 else 'needs'} support this week." if risk
                   else "No one is below Good this week.")
    body = [f"Your weekly ratings, {start:%d %b} to {end:%d %b} (only you see these).", summary, "\n".join(lines),
            f"Reasons given for delays: {reasons}.",
            "How the rating is worked out, and each person's KPIs, are in the coordinator console under Ratings."]
    return "\n\n".join(body), cost


def send_if_due(now: datetime) -> bool:
    """Keep the ratings and send the report on the first working day of the week, once."""
    ceo = services.ceo()
    t = local_now(now)
    today = t.date()
    monday = today - timedelta(days=today.weekday())
    first = next((monday + timedelta(days=i) for i in range(5) if calendar.is_working_day(monday + timedelta(days=i))), None)
    if ceo is None or today != first or t.strftime("%H:%M") < policies.resolve("kpi_report_time"):
        return False
    week = monday.isoformat()
    if AgentAction.objects.filter(trigger=TRIGGER, detail__week=week).exists():
        return False
    before = kpi.previous_scores(today)
    rows = kpi.snapshot(today)
    if not rows:
        return False
    text, cost = compose(rows, before, today)
    message = services.post_as_agent(services.conversation_for(ceo), text)
    AgentAction.objects.create(trigger=TRIGGER, target=ceo, reason="Weekly ratings for the CEO", message=message, cost_usd=cost,
                               detail={"week": week, "people": len(rows)})
    return True
