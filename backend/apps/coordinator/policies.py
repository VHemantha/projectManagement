"""The agent's rules: the defaults from AFIT's specification (section 4) and how a rule is resolved
for a job or a person. Numbers are compared by code, never by the AI.

Precedence (most specific first): job, person, client, team, company. A rule outside its
effective dates is skipped. Every change is a new version; the old one stays for the record.
"""
import re
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import AgentPolicy


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    default: object
    kind: str  # "number" | "time" | "choice"
    help: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


RULES = [
    Rule("precheck_due_days", "Pre-check due (days after the job starts)", 3, "number",
         "Target for finishing the pre-check, counted from the day the job starts.", 1, 30),
    Rule("day_basis", "How days are counted", "working", "choice",
         "Working days skip weekends, public holidays and the person's leave.", choices=("working", "calendar")),
    Rule("day_cutoff", "End of the working day", "17:00", "time", "A deadline falls due at this time on its last day."),
    Rule("urgent_first_check_days", "Urgent jobs: first check (days after the job starts)", 1, "number",
         "Urgent and high-priority jobs are checked this early if nothing has happened.", 0, 10),
    Rule("preparation_warn_days", "Preparation: ask when the deadline is this close (days)", 2, "number",
         "When the deadline is this many days away or less and progress is uncertain, the agent asks what remains.", 0, 14),
    Rule("hours_warning_pct", "Hours: warn at (% of budget)", 100, "number",
         "A warning before the tolerance is reached, on actual or forecast hours.", 50, 200),
    Rule("hours_tolerance_pct", "Hours: tolerance (% of budget)", 125, "number",
         "Exactly this is within tolerance; anything above starts the over-tolerance follow-up.", 100, 300),
    Rule("timesheet_check_time", "Timesheet check (local time)", "09:30", "time",
         "Each morning the previous working day's timesheet is checked."),
    Rule("timesheet_min_hours", "Timesheet minimum (hours a day)", 7.5, "number",
         "Below this, unless on leave, a holiday or a part-time day, the agent asks for the missing time.", 0, 24),
    Rule("timesheet_target_hours", "Timesheet target (hours a day)", 8, "number", "The normal full day.", 0, 24),
    Rule("timesheet_recheck_hours", "Timesheet recheck after (hours)", 2.5, "number",
         "If still short after this, the team lead is told.", 0.5, 24),
    Rule("max_follow_ups", "Follow-ups before escalating", 2, "number",
         "After this many unanswered or unresolved follow-ups the agent escalates instead of asking again.", 1, 10),
    Rule("communication", "Communication intensity", "normal", "choice",
         "Quiet: only risks and deadlines. Normal: as the rules say. Close: earlier and more frequent checks. "
         "Critical risk alerts are never suppressed.", choices=("quiet", "normal", "close")),
]
BY_KEY = {r.key: r for r in RULES}
SCOPE_ORDER = [AgentPolicy.Scope.JOB, AgentPolicy.Scope.PERSON, AgentPolicy.Scope.CLIENT, AgentPolicy.Scope.TEAM, AgentPolicy.Scope.COMPANY]


class PolicyError(ValueError):
    pass


def validate(key: str, value):
    rule = BY_KEY.get(key)
    if rule is None:
        raise PolicyError(f"Unknown rule: {key}.")
    if rule.kind == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise PolicyError(f"{rule.label}: give a number.") from None
        if (rule.minimum is not None and number < rule.minimum) or (rule.maximum is not None and number > rule.maximum):
            raise PolicyError(f"{rule.label}: between {rule.minimum:g} and {rule.maximum:g}.")
        return int(number) if number.is_integer() else number
    if rule.kind == "time":
        if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise PolicyError(f"{rule.label}: give a time as HH:MM.")
        return value
    if value not in rule.choices:
        raise PolicyError(f"{rule.label}: one of {', '.join(rule.choices)}.")
    return value


def resolve(key: str, *, job=None, person=None, at=None):
    """The value that applies to this job and person now: the most specific active rule, else
    the default from the specification."""
    at = at or timezone.now()
    candidates = []
    if job is not None:
        candidates.append((AgentPolicy.Scope.JOB, str(job.pk)))
        if job.project.client_id:
            candidates.append((AgentPolicy.Scope.CLIENT, str(job.project.client_id)))
        team = (job.project.client.team_id if job.project.client_id else None) or job.project.primary_team_id
        if team:
            candidates.append((AgentPolicy.Scope.TEAM, str(team)))
    if person is not None:
        candidates.append((AgentPolicy.Scope.PERSON, str(person.pk)))
    candidates.append((AgentPolicy.Scope.COMPANY, ""))
    rows = {(p.scope, p.scope_id): p for p in AgentPolicy.objects.filter(key=key, active=True, effective_from__lte=at)
            if p.expires_at is None or p.expires_at > at}
    for scope in SCOPE_ORDER:
        for cand_scope, cand_id in candidates:
            if cand_scope == scope and (cand_scope, cand_id) in rows:
                return rows[(cand_scope, cand_id)].value
    return BY_KEY[key].default


@transaction.atomic
def set_rule(key: str, value, *, scope: str = AgentPolicy.Scope.COMPANY, scope_id: str = "", user=None, note: str = "",
             effective_from=None, expires_at=None) -> AgentPolicy:
    """A new version of the rule for this scope; the previous one is kept, no longer active."""
    value = validate(key, value)
    if scope not in AgentPolicy.Scope.values:
        raise PolicyError("Unknown scope.")
    if scope != AgentPolicy.Scope.COMPANY and not scope_id:
        raise PolicyError("Say which team, client, person or job the rule is for.")
    if scope == AgentPolicy.Scope.COMPANY:
        scope_id = ""
    previous = AgentPolicy.objects.select_for_update().filter(key=key, scope=scope, scope_id=scope_id, active=True).first()
    if previous:
        previous.active = False
        previous.save(update_fields=["active"])
    return AgentPolicy.objects.create(
        key=key, scope=scope, scope_id=scope_id, value=value, version=(previous.version + 1) if previous else 1, note=note[:300],
        effective_from=effective_from or timezone.now(), expires_at=expires_at, approved_by=user)


def over_tolerance(actual_or_forecast: float, budget: float, tolerance_pct: float) -> bool:
    """Spec: exactly the tolerance is within it; strictly above triggers the over-tolerance rule."""
    return budget > 0 and actual_or_forecast / budget * 100 > tolerance_pct
