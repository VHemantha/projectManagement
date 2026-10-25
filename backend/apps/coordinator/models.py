"""The AI project coordination agent (AFIT's developer specification, 25 Oct 2026): its controls,
policies, audit trail and the work calendars its timesheet and capacity rules rely on.

The agent itself is a user account (is_agent) that writes in the Messages section. Only the CEO
sets its policies and controls; everyone else may only chat with it.
"""
from django.conf import settings
from django.db import models


class CoordinatorSettings(models.Model):
    """The agent's master switches (one row). New installs start in shadow mode: every message the
    agent would send to staff goes to the CEO instead, for review, until the CEO turns it off."""

    paused = models.BooleanField(default=False)  # emergency pause: no checks, no messages
    shadow_mode = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default="Pacific/Auckland")
    daily_cost_cap_usd = models.FloatField(default=5.0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls) -> "CoordinatorSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AgentPolicy(models.Model):
    """One rule the agent applies (spec section 4). A change is a new version, never an edit: the
    old row stays, with who approved it and when, so every past decision can be explained."""

    class Scope(models.TextChoices):
        COMPANY = "company", "Company"
        TEAM = "team", "Team"
        CLIENT = "client", "Client"
        PERSON = "person", "Person"
        JOB = "job", "Job"

    key = models.CharField(max_length=40)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.COMPANY)
    scope_id = models.CharField(max_length=40, blank=True)  # the team/client/person/job id; empty for company
    value = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)  # the latest version of this key and scope
    note = models.CharField(max_length=300, blank=True)
    effective_from = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key", "scope", "scope_id", "-version"]
        indexes = [models.Index(fields=["key", "scope", "scope_id", "active"])]


class AuditEntry(models.Model):
    """Who asked the agent's controls to do what, and whether it was allowed. Refused attempts
    are kept too (spec: a delegated admin changing a CEO-only policy is denied and logged)."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=200, blank=True)
    allowed = models.BooleanField(default=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AgentAction(models.Model):
    """Everything the agent does or would have done (in shadow mode): the trigger, the target, why,
    and the message it sent."""

    trigger = models.CharField(max_length=60)
    target = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    issue = models.ForeignKey("issues.Issue", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.CharField(max_length=500, blank=True)
    message = models.ForeignKey("chat.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    shadow = models.BooleanField(default=False)
    cost_usd = models.FloatField(default=0)  # what any AI call for this action cost (the daily cap)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AgentCase(models.Model):
    """One matter the agent is following up: a job, the person responsible, and what is at stake
    (e.g. the pre-check is overdue). It keeps the original and any revised date apart, counts the
    follow-ups, and says when to look again, so nobody is asked the same thing twice."""

    class Kind(models.TextChoices):
        URGENT_INACTIVE = "urgent_inactive", "Urgent job with no activity"
        PRECHECK_DUE = "precheck_due", "Pre-check due soon"
        PRECHECK_OVERDUE = "precheck_overdue", "Pre-check overdue"
        PREP_DUE = "prep_due", "Preparation due soon"
        PREP_OVERDUE = "prep_overdue", "Preparation overdue"
        PROMISE_MISSED = "promise_missed", "Revised date missed"

    class State(models.TextChoices):
        ASKED = "asked", "Asked, waiting for a reply"
        ANSWERED = "answered", "Answered"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"

    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="agent_cases")
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_cases")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    state = models.CharField(max_length=10, choices=State.choices, default=State.ASKED)
    due_date = models.DateField(null=True, blank=True)  # the original date at stake
    revised_due = models.DateField(null=True, blank=True)  # the date the person gave, kept apart
    asked = models.PositiveIntegerField(default=0)  # messages sent about it, the first included
    last_asked_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True)
    escalated_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-opened_at", "-id"]
        indexes = [models.Index(fields=["person", "state"]), models.Index(fields=["issue", "kind", "state"])]

    @property
    def is_open(self) -> bool:
        return self.state != self.State.RESOLVED


class Commitment(models.Model):
    """What a person said in reply: hours still needed, the date they expect to finish, the cause of
    any delay and whether they need help. Read from their own words; the figures that follow from
    it (forecast hours against the budget) are worked out by code."""

    class Cause(models.TextChoices):
        NONE = "none", "None given"
        CLIENT_DOCUMENTS = "client_documents", "Waiting for client documents"
        BOOKKEEPING_ERRORS = "bookkeeping_errors", "Bookkeeping errors"
        SCOPE_CHANGE = "scope_change", "Client scope change"
        COMPLEXITY = "complexity", "More complex than expected"
        REWORK = "rework", "Rework after review"
        DEPENDENCY = "dependency", "Waiting on someone else"
        WORKLOAD = "workload", "Other work"
        PERSONAL = "personal", "Personal / leave"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        KEPT = "kept", "Kept"
        MISSED = "missed", "Missed"
        SUPERSEDED = "superseded", "Replaced by a later one"

    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commitments")
    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="commitments")
    case = models.ForeignKey(AgentCase, null=True, blank=True, on_delete=models.SET_NULL, related_name="commitments")
    eta_date = models.DateField(null=True, blank=True)
    remaining_hours = models.FloatField(null=True, blank=True)
    percent_complete = models.FloatField(null=True, blank=True)  # as claimed: checked against the job's record
    cause = models.CharField(max_length=20, choices=Cause.choices, default=Cause.NONE)
    blockers = models.CharField(max_length=300, blank=True)
    needs_help = models.BooleanField(default=False)
    source_message = models.ForeignKey("chat.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


# --- work calendars ---------------------------------------------------------------------------------

def default_week() -> list[float]:
    return [8, 8, 8, 8, 8, 0, 0]  # Monday to Sunday


class WorkSchedule(models.Model):
    """A person's normal hours per weekday (Monday first). Without one, Monday to Friday, 8 hours."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="work_schedule")
    hours = models.JSONField(default=default_week)
    note = models.CharField(max_length=200, blank=True)  # e.g. "part-time, 3 days"
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)


class LeaveRecord(models.Model):
    """Leave a person requests and the CEO approves. Approved leave stops false timesheet warnings."""

    class Kind(models.TextChoices):
        ANNUAL = "annual", "Annual leave"
        SICK = "sick", "Sick leave"
        TRAINING = "training", "Training"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_records")
    start_date = models.DateField()
    end_date = models.DateField()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ANNUAL)
    hours_per_day = models.FloatField(null=True, blank=True)  # part day; empty = the whole working day
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]


class PublicHoliday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["date"]
