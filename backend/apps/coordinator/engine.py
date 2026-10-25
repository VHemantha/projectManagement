"""The coordination agent's scheduled checks (spec sections 5, 10 and 14): every 15 minutes, look at
every open job silently; open a case when something needs a person's attention; ask once, follow up
after the reply window, escalate to the team lead after the follow-up limit; close the case when
the job record shows it is resolved. Messages go out only within working hours, grouped into one
per person. In shadow mode they go to the CEO instead, for review.

Everything here is decided by code from the job records; no AI is involved in the checks.
"""
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from . import calendar, policies, services
from .facts import URGENT, has_activity, job_facts, leads_for, local_now, open_jobs, responsible, tz, within_window, working_days_late
from .models import AgentAction, AgentCase, Commitment, CoordinatorSettings
from .texts import ask_text, escalation_text, group_for_person, shadow_digest

logger = logging.getLogger(__name__)
K = AgentCase.Kind
S = AgentCase.State


def conditions(issue, person, f, today, intensity: str) -> list[tuple[str, object]]:
    """What needs attention on this job now: [(case kind, the date at stake)]. Overdue work is
    always raised, whatever the communication intensity (critical risks are never suppressed)."""
    urgent = issue.priority in URGENT
    out = []
    if not f.precheck_done:
        if today > f.precheck_due:
            out.append((K.PRECHECK_OVERDUE, f.precheck_due))
        elif calendar.add_days(today, 1, user=person) >= f.precheck_due and (intensity != "quiet" or urgent):
            out.append((K.PRECHECK_DUE, f.precheck_due))
        first_check = int(policies.resolve("urgent_first_check_days", job=issue, person=person))
        if (urgent or intensity == "close") and not has_activity(issue) and working_days_late(f.start, today, person) >= first_check:
            out.append((K.URGENT_INACTIVE, f.precheck_due))
    if not f.prep_done and f.prep_due:
        warn = int(policies.resolve("preparation_warn_days", job=issue, person=person)) + (1 if intensity == "close" else 0)
        if today > f.prep_due:
            out.append((K.PREP_OVERDUE, f.prep_due))
        elif calendar.add_days(today, warn, user=person) >= f.prep_due and (intensity != "quiet" or urgent):
            out.append((K.PREP_DUE, f.prep_due))
    # A date the person gave has passed and the work is not done: raised until they give a new
    # date (a newer commitment) or the job record shows the stage is done.
    latest = Commitment.objects.filter(issue=issue, person=person).exclude(status=Commitment.Status.SUPERSEDED).first()
    if (latest and latest.eta_date and latest.eta_date < today and latest.verified_at is None
            and latest.status in (Commitment.Status.OPEN, Commitment.Status.MISSED)):
        if latest.status == Commitment.Status.OPEN:
            latest.status = Commitment.Status.MISSED
            latest.save(update_fields=["status"])
        out.append((K.PROMISE_MISSED, latest.eta_date))
    return out


def case_for(issue, person, kind: str, due) -> AgentCase:
    case = AgentCase.objects.filter(issue=issue, person=person, kind=kind).exclude(state=S.RESOLVED).first()
    if case is None:
        case = AgentCase.objects.create(issue=issue, person=person, kind=kind, due_date=due)
    return case


def decide(case: AgentCase, now: datetime) -> str:
    """"ask" (first message or a follow-up), "escalate", or "" (nothing to do yet)."""
    window = timedelta(hours=float(policies.resolve("reply_window_hours", job=case.issue, person=case.person)))
    limit = int(policies.resolve("max_follow_ups", job=case.issue, person=case.person))
    if case.state == S.ESCALATED:
        return ""
    if case.state == S.ANSWERED:
        if case.revised_due:  # they gave a date: wait for it (a missed date opens its own case)
            return ""
        if case.answered_at and now >= case.answered_at + window:
            return "ask" if case.asked <= limit else "escalate"
        return ""
    if case.asked == 0:
        return "ask"
    if case.last_asked_at and now >= case.last_asked_at + window:
        return "ask" if case.asked <= limit else "escalate"
    return ""


def tick(now: datetime | None = None) -> dict:
    """One round of checks. Returns what happened (for the log and the tests)."""
    s = CoordinatorSettings.get()
    if s.paused:
        return {"paused": True}
    now = now or timezone.now()
    today = local_now(now).date()
    sending = within_window(now)
    outbox: dict = defaultdict(list)  # person -> [(case, text)]
    escalations: dict = defaultdict(list)  # lead or CEO -> [(case, text)]
    live = set()
    for issue in open_jobs():
        person = responsible(issue)
        if person is None:
            continue
        f = job_facts(issue, person)
        verify_commitments(issue, person, f, now)
        intensity = policies.resolve("communication", job=issue, person=person)
        for kind, due in conditions(issue, person, f, today, intensity):
            case = case_for(issue, person, kind, due)
            live.add(case.pk)
            action = decide(case, now) if sending else ""
            if action == "ask":
                outbox[person].append((case, ask_text(case, f, today, follow_up=case.asked > 0)))
            elif action == "escalate":
                target = (leads_for(issue, exclude=person) or [services.ceo()])[0]
                if target is not None:
                    escalations[target].append((case, escalation_text(case, f)))
    closed = 0
    for case in AgentCase.objects.exclude(state=S.RESOLVED).exclude(pk__in=live):
        _close(case, "No longer needs attention: the stage is done, a new date was given, or the job closed.", now)
        closed += 1
    sent = deliver(outbox, escalations, now, shadow=s.shadow_mode) if sending else {"people": 0, "escalations": 0}
    from .briefing import send_if_due

    briefing = send_if_due(now)
    return {"cases_open": len(live), "closed": closed, **sent, "briefing": briefing, "sending": sending}


def _close(case: AgentCase, reason: str, now) -> None:
    case.state, case.closed_at, case.closed_reason = S.RESOLVED, now, reason[:200]
    case.save(update_fields=["state", "closed_at", "closed_reason"])


PRECHECK_KINDS = (K.PRECHECK_DUE, K.PRECHECK_OVERDUE, K.URGENT_INACTIVE)


def verify_commitments(issue, person, f, now) -> None:
    """A promise is kept only when the job record shows the stage done (spec: verify completion
    from a PM event, not from chat assurances)."""
    for c in Commitment.objects.filter(issue=issue, person=person, status__in=[Commitment.Status.OPEN, Commitment.Status.MISSED]).select_related("case"):
        stage_done = f.precheck_done if (c.case and c.case.kind in PRECHECK_KINDS) else f.prep_done
        if stage_done and c.verified_at is None:
            if c.status == Commitment.Status.OPEN:
                c.status = Commitment.Status.KEPT  # done by the date given
            c.verified_at = now  # a missed one stays missed: done, but after the date given
            c.save(update_fields=["status", "verified_at"])


@transaction.atomic
def deliver(outbox: dict, escalations: dict, now, *, shadow: bool) -> dict:
    """Send each person one message with everything for them, and each lead their escalations. In
    shadow mode nothing goes to staff: the CEO gets one digest of what would have been sent."""
    digest = []
    for person, items in outbox.items():
        text = group_for_person(person, [t for _, t in items])
        message = None if shadow else services.post_as_agent(services.conversation_for(person), text)
        digest.append((person, text))
        for case, _ in items:
            case.asked += 1
            case.last_asked_at = now
            if case.state == S.ANSWERED:
                case.state = S.ASKED
            case.save(update_fields=["asked", "last_asked_at", "state"])
            AgentAction.objects.create(trigger=case.kind, target=person, issue=case.issue, reason=f"{case.get_kind_display()} — message {case.asked}",
                                       message=message, shadow=shadow)
    for lead, items in escalations.items():
        text = group_for_person(lead, [t for _, t in items], escalation=True)
        message = None if shadow else services.post_as_agent(services.conversation_for(lead), text)
        digest.append((lead, text))
        for case, _ in items:
            case.state, case.escalated_to = S.ESCALATED, lead
            case.save(update_fields=["state", "escalated_to"])
            AgentAction.objects.create(trigger="escalation", target=lead, issue=case.issue,
                                       reason=f"Escalated: {case.get_kind_display()} ({case.person.display_name})", message=message, shadow=shadow)
    if shadow and digest:
        ceo = services.ceo()
        if ceo is not None:
            services.post_as_agent(services.conversation_for(ceo), shadow_digest(digest))
    return {"people": len(outbox), "escalations": len(escalations)}


def end_of_day(day) -> datetime:
    cutoff = policies.resolve("day_cutoff")
    h, m = (int(x) for x in cutoff.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=tz())
