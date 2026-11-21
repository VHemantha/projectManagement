"""Who logged less than 7.5 hours (AFIT, 21 Nov 2026): once each working day, at the briefing time, the
Practice Manager AI tells the CEO who logged under 7.5 hours on the last working day (less for approved
leave, a holiday or a part-time day), and tells each team lead the same about the people they lead.
Worked out by code from the timesheets; no AI is involved. In shadow mode the team leads' notes go to the
CEO instead, for review.
"""
from apps.timesheets.efficiency import TARGET_HOURS, under_target

from . import calendar, policies, services
from .facts import local_now
from .models import AgentAction

TRIGGER = "low_hours"


def _line(row) -> str:
    short = round(row["expected"] - row["logged"], 2)
    of = f"{row['expected']:g}h expected" if row["expected"] < TARGET_HOURS else f"{TARGET_HOURS:g}h"
    return f"• {row['user'].display_name}: {row['logged']:g}h logged of {of} ({short:g}h short)"


def text_for(rows: list[dict], day, *, lead: bool) -> str:
    who = "the people you lead" if lead else "the team"
    head = (f"Hours logged on {day:%A %d %B}: {len(rows)} of {who} logged under {TARGET_HOURS:g} hours.")
    tail = ("Please check in with them: their timesheet may be incomplete, or they may need work or help."
            if lead else "Their team leads have been told. Time not on a job can be logged to Idle, Administration or Training.")
    return "\n".join([head, *(_line(r) for r in rows), "", tail])


def send_if_due(now) -> dict:
    """Once a working day, after the briefing time: {"day", "under", "leads"}; {} when not due."""
    from apps.accounts.models import User
    from apps.teams.leads import led_people
    from apps.teams.models import TeamMembership

    from django.conf import settings

    if not getattr(settings, "COORDINATOR_LOW_HOURS", True):
        return {}
    t = local_now(now)
    if not calendar.is_working_day(t.date()) or t.strftime("%H:%M") < policies.resolve("ceo_briefing_time"):
        return {}
    day = calendar.previous_working_day(t.date())
    if day is None or AgentAction.objects.filter(trigger=TRIGGER, detail__date=day.isoformat()).exists():
        return {}
    from .models import CoordinatorSettings

    shadow = CoordinatorSettings.get().shadow_mode
    staff = list(User.objects.filter(is_active=True, is_agent=False).exclude(role=User.Role.CEO))
    rows = under_target(staff, day)
    ceo = services.ceo()
    message = None
    if ceo is not None and rows:
        message = services.post_as_agent(services.conversation_for(ceo), text_for(rows, day, lead=False))
    told = 0
    lead_ids = set(TeamMembership.objects.filter(role=TeamMembership.Role.LEAD, user__is_active=True).values_list("user_id", flat=True))
    for lead in User.objects.filter(id__in=lead_ids).exclude(role=User.Role.CEO):
        mine = {p.id for p in led_people(lead)}
        theirs = [r for r in rows if r["user"].id in mine]
        if not theirs:
            continue
        text = text_for(theirs, day, lead=True)
        if shadow:
            if ceo is not None:
                services.post_as_agent(services.conversation_for(ceo), f"Shadow mode — I would have sent to {lead.display_name}:\n{text}")
        else:
            services.post_as_agent(services.conversation_for(lead), text)
        AgentAction.objects.create(trigger=TRIGGER, target=lead, reason=f"Low hours on {day:%d %b} for {lead.display_name}", shadow=shadow,
                                   detail={"date": day.isoformat(), "people": [r["user"].id for r in theirs], "lead": True})
        told += 1
    AgentAction.objects.create(trigger=TRIGGER, target=ceo, reason=f"Low hours on {day:%d %b}: {len(rows)} under {TARGET_HOURS:g}h",
                               message=message, detail={"date": day.isoformat(), "people": [r["user"].id for r in rows]})
    return {"day": day.isoformat(), "under": len(rows), "leads": told}
