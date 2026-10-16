"""AI pre-check: what a job needs before it can run, and the history of every run.

The pre-check is a quality gate before human internal review. Nothing in this app changes a
job's status or marks it reviewed, and no run or finding is ever overwritten: each run is a
new AIPrecheck, and each human decision on a finding is a new AIFeedback row.
"""
import re

from django.conf import settings
from django.db import models

_FOLDER_URL = re.compile(r"/folders/([A-Za-z0-9_-]{10,})")
_BARE_ID = re.compile(r"^[A-Za-z0-9_:\-. ]{3,200}$")


def folder_id_from(value: str) -> str:
    """A Drive folder id from a pasted folder link, or the id itself."""
    value = (value or "").strip()
    match = _FOLDER_URL.search(value)
    if match:
        return match.group(1)
    if "id=" in value:
        return value.split("id=", 1)[1].split("&", 1)[0]
    return value if _BARE_ID.match(value) and "/" not in value else ""


# The business nature the pre-check works to. "auto": decided by the AI from the questionnaire
# and last year's accounts; the others fix it for the task.
PRECHECK_TYPES = [
    ("auto", "Decide from the questionnaire"),
    ("residential_rental", "Residential rental"),
    ("general", "General business"),
    ("investment", "Investment"),
]

# The three documents a pre-check cannot start without. A person may say where each one is: a
# path inside the task folder or a Drive link, several separated by ";".
KEY_DOCUMENT_ROLES = ("questionnaire", "last_year_fs", "last_year_workpapers")
# Other places a person can set on the card: this year's draft statements (for the review) and
# this year's general ledger (an optional pre-check input).
CARD_PATH_ROLES = KEY_DOCUMENT_ROLES + ("draft_fs", "general_ledger")


class JobFolder(models.Model):
    """The Google Drive folder that holds a task's documents, and the business nature the
    pre-check works to (decided from the questionnaire unless a person fixes it)."""

    issue = models.OneToOneField("issues.Issue", on_delete=models.CASCADE, related_name="drive_folder")
    folder_id = models.CharField(max_length=200)
    folder_url = models.CharField(max_length=500, blank=True)
    precheck_type = models.CharField(max_length=30, choices=PRECHECK_TYPES, default="auto")
    # {"questionnaire": "2026/Client Questionnaire.pdf", ...}: where each key document is. Empty: search the folder.
    key_paths = models.JSONField(default=dict, blank=True)
    # Accountant-confirmed settings (general business and investment briefs, 16 Oct 2026):
    # {"year_start", "year_end" (ISO dates), "xero_complete", "ird_access", "related_records" (yes|no|"")}.
    accountant_settings = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)


class DirectionItem(models.Model):
    """One item of a job's Direction Note: something the job must cover. Typed by a person, or
    drafted by the AI from the client's past jobs and the job folder (and then editable)."""

    class Origin(models.TextChoices):
        PERSON = "person", "Written by a person"
        AI = "ai", "Drafted by AI"

    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="direction_items")
    ref = models.CharField(max_length=10)  # D1, D2, ... stable within the job
    text = models.CharField(max_length=500)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.PERSON)
    # For AI-drafted items: why it was suggested, and whether that came from the client's
    # history, from what is in the folder now, or from what every job of this kind needs.
    reason = models.CharField(max_length=300, blank=True)
    basis = models.CharField(max_length=20, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["issue", "ref"], name="direction_ref_unique_per_job")]

    def __str__(self):
        return f"{self.ref}: {self.text}"


class AIPrecheck(models.Model):
    """One run of the pre-check on one job. Every run is kept."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        PARTIAL = "partial", "Partial (budget reached)"
        FAILED = "failed", "Failed"

    class Verdict(models.TextChoices):
        READY = "ready", "Ready for review"
        READY_WITH_EXCEPTIONS = "ready_with_exceptions", "Ready with exceptions"
        NOT_READY = "not_ready", "Not ready"

    class Kind(models.TextChoices):
        PRECHECK = "precheck", "Pre-check"
        DRAFT = "draft", "Direction Note draft only"
        REVIEW = "review", "Review of the draft financial statements"

    run_id = models.CharField(max_length=64, unique=True)  # also the agent's LangGraph thread id
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PRECHECK)
    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="prechecks")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    verdict = models.CharField(max_length=30, choices=Verdict.choices, blank=True)
    summary = models.CharField(max_length=400, blank=True)
    coverage_addressed = models.PositiveIntegerField(default=0)
    coverage_total = models.PositiveIntegerField(default=0)
    counts = models.JSONField(default=dict)  # open findings by severity
    direction_items = models.JSONField(default=list)  # [{id, text, addressed}] as checked in this run
    trail = models.JSONField(default=dict)  # the five "how the AI got here" steps, with real counts
    progress = models.JSONField(default=list)  # live events while running
    skipped = models.JSONField(default=list)  # what a partial run did not get to, and why
    # This year's documents against last year's accounts: lines, checks, bank summaries and
    # commentary. Every figure in it was produced by code in the agent.
    analysis = models.JSONField(default=dict)
    precheck_type = models.CharField(max_length=30, default="general")
    readiness = models.CharField(max_length=40, blank=True)  # the verdict in the type's own words
    requests = models.JSONField(default=list)  # drafted requests for missing information; never sent
    # The pre-check itself: decision, key documents, business nature with its reasoning, each item
    # requested / already provided / not needed with its reason and sources, and the drafted email.
    precheck = models.JSONField(default=dict)
    # A review round: the draft reviewed, findings (with refs given by the PM application),
    # resolved findings, a verdict on each assumption, and the code checks.
    review = models.JSONField(default=dict)
    failure_reason = models.CharField(max_length=500, blank=True)
    usage = models.JSONField(default=dict)  # totals, calls, cost, cache share, budget
    models_used = models.JSONField(default=dict)
    versions = models.JSONField(default=dict)  # prompt, parser and skill versions
    knowledge_ids = models.JSONField(default=list)
    demo = models.BooleanField(default=False)  # produced by the scripted demo models, not Claude
    duration_s = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI pre-check"

    def __str__(self):
        return f"Pre-check {self.run_id[:8]} of {self.issue_id} ({self.status})"


class AIEvidence(models.Model):
    """A quoted source passage. Built by code from the model's citations, never written by a
    model."""

    precheck = models.ForeignKey(AIPrecheck, on_delete=models.CASCADE, related_name="evidence")
    evidence_id = models.CharField(max_length=40)
    file_id = models.CharField(max_length=400)
    file_name = models.CharField(max_length=400)
    location = models.CharField(max_length=300)
    quote = models.TextField()
    drive_url = models.CharField(max_length=1000, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["precheck", "evidence_id"], name="evidence_unique_per_run")]


class AIFinding(models.Model):
    precheck = models.ForeignKey(AIPrecheck, on_delete=models.CASCADE, related_name="findings")
    finding_id = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)
    direction_ref = models.CharField(max_length=20, default="none")
    area = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20)  # addressed | exception | missing | unclear
    severity = models.CharField(max_length=10)  # high | medium | low
    kind = models.CharField(max_length=20)  # fact | rule | client_preference | ai_suggestion
    title = models.CharField(max_length=300)
    why = models.CharField(max_length=500)
    source = models.CharField(max_length=10)  # rule | ai
    confidence = models.CharField(max_length=10)
    evidence = models.ManyToManyField(AIEvidence, related_name="findings", blank=True)

    class Meta:
        ordering = ["order", "id"]


class ModelRun(models.Model):
    """Audit log of every model call in a run: which model, which prompt and skill versions,
    what knowledge was in scope, and the tokens used."""

    precheck = models.ForeignKey(AIPrecheck, on_delete=models.CASCADE, related_name="model_runs")
    node = models.CharField(max_length=20)  # read | read_image | judge | escalate | draft
    task_id = models.CharField(max_length=80, blank=True)
    model = models.CharField(max_length=80)
    calls = models.PositiveIntegerField(default=1)
    input_tokens = models.PositiveIntegerField(default=0)  # uncached input
    output_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    prompt_version = models.CharField(max_length=40, blank=True)
    skill_versions = models.JSONField(default=dict)
    knowledge_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class AIFeedback(models.Model):
    """A person's decision on a finding. Append-only: the latest row is the current decision,
    and "cleared" undoes it."""

    class Disposition(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        NEEDS_CLARIFICATION = "needs_clarification", "Needs clarification"
        CLEARED = "cleared", "Cleared"

    finding = models.ForeignKey(AIFinding, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    disposition = models.CharField(max_length=30, choices=Disposition.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class PrecheckLesson(models.Model):
    """A correction by AFIT staff that the pre-check applies from then on: "this was not needed
    because …", "the reason was wrong", "you missed …". Not training: lessons are given to the
    model with each pre-check they apply to, and every run lists the ones it applied.

    A lesson applies at once to the client it came from. Applying it more widely - the project, the
    team (workspace) or every client of that business nature - needs a lead or an admin to approve
    it (AFIT, 5 Oct 2026). Since 12 Oct 2026 lessons also come from the review (a finding closed as
    not an issue, a wrong reason, something the AI missed), and the AI drafts each one as a rule
    (when it applies, what to do, why): a learned skill the pre-check, the review and Ask apply."""

    class Scope(models.TextChoices):
        CLIENT = "client", "This client"
        PROJECT = "project", "This project"
        TEAM = "team", "This workspace (team)"
        FIRM = "firm", "All clients of this business nature"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Waiting for approval"
        DISABLED = "disabled", "Switched off"

    class Kind(models.TextChoices):
        NOT_NEEDED = "not_needed", "Not needed"
        WRONG_REASON = "wrong_reason", "Wrong reason"
        MISSED = "missed", "Missed item"
        OTHER = "other", "Other"

    client_scope = models.CharField(max_length=100)  # the client (or workspace) it came from
    project_scope = models.CharField(max_length=40, blank=True)  # "project-<id>" it came from
    team_scope = models.CharField(max_length=40, blank=True)  # "team-<id>" it came from
    source = models.CharField(max_length=10, choices=[("precheck", "Pre-check"), ("review", "Review"), ("ask", "Ask")], default="precheck")
    finding = models.ForeignKey("ReviewFinding", null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    # The rule the AI drafted from the correction; empty until drafted (the note applies meanwhile).
    rule_title = models.CharField(max_length=200, blank=True)
    rule_when = models.TextField(max_length=600, blank=True)
    rule_do = models.TextField(max_length=800, blank=True)
    rule_why = models.TextField(max_length=600, blank=True)
    drafting = models.CharField(max_length=10, blank=True)  # "" | drafting | drafted | failed
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.CLIENT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    precheck_type = models.CharField(max_length=30, blank=True)  # business nature of the run it came from
    item = models.CharField(max_length=300, blank=True)
    note = models.TextField(max_length=1000)
    issue = models.ForeignKey("issues.Issue", null=True, blank=True, on_delete=models.SET_NULL, related_name="precheck_lessons")
    run = models.ForeignKey(AIPrecheck, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


# --- the review of the draft financial statements -------------------------------------------------

class Assumption(models.Model):
    """An assumption or judgement the preparer used, recorded on the task as the accounts are
    prepared: what was decided, on what basis, with what evidence. The review tests each one.
    An edit keeps the earlier wording in `history`; nothing is deleted, only withdrawn."""

    class Area(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSES = "expenses", "Expenses"
        ASSETS = "assets", "Fixed assets and depreciation"
        ACCRUALS = "accruals", "Accruals and prepayments"
        LOANS = "loans", "Loans and interest"
        PROPERTY = "property", "Property"
        PRIVATE_USE = "private_use", "Private use and home office"
        RELATED = "related", "Related parties and shareholders"
        TAX = "tax", "Tax and GST"
        OTHER = "other", "Other"

    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="assumptions")
    ref = models.CharField(max_length=10)  # A1, A2, ... stable within the task
    area = models.CharField(max_length=20, choices=Area.choices, default=Area.OTHER)
    fs_line = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    judgement = models.TextField(max_length=2000)
    basis = models.TextField(max_length=2000, blank=True)
    evidence = models.CharField(max_length=500, blank=True)  # a document name, path or link
    status = models.CharField(max_length=10, choices=[("active", "Active"), ("withdrawn", "Withdrawn")], default="active")
    history = models.JSONField(default=list)  # earlier versions: [{judgement, basis, ..., by, at}]
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["issue", "ref"], name="assumption_ref_per_task")]


class ReviewFinding(models.Model):
    """One problem in the draft statements, kept across review rounds under one ref (R1, R2...)
    until it is resolved or the reviewer closes it. Raised by the AI, or by a person ("something
    the AI missed"). Each response is also a ReviewResponse row, so the history is kept."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed by the reviewer"

    class Response(models.TextChoices):
        AGREE = "agree", "Agree - to be fixed"
        FIXED = "fixed", "Fixed"
        NOT_AN_ISSUE = "not_an_issue", "Not an issue"
        WRONG_REASON = "wrong_reason", "Wrong reason"

    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="review_findings")
    ref = models.CharField(max_length=10)
    origin = models.CharField(max_length=10, choices=[("ai", "Raised by AI"), ("person", "Raised by a person")], default="ai")
    first_run = models.ForeignKey(AIPrecheck, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_run = models.ForeignKey(AIPrecheck, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    area = models.CharField(max_length=100, blank=True)
    fs_line = models.CharField(max_length=200, blank=True)
    text = models.TextField(max_length=1000)  # the issue
    why = models.TextField(max_length=1000, blank=True)
    action = models.TextField(max_length=500, blank=True)
    severity = models.CharField(max_length=10, default="medium")
    sources = models.JSONField(default=list)  # as shown on the card: [{id, label, evidence_id}]
    assumptions = models.JSONField(default=list)  # A refs
    flags = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolved_reason = models.CharField(max_length=500, blank=True)
    response = models.CharField(max_length=20, choices=Response.choices, blank=True)
    note = models.TextField(max_length=1000, blank=True)
    responded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    responded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["issue", "ref"], name="review_finding_ref_per_task")]


class ReviewResponse(models.Model):
    """Every response a person gave to a review finding, in order: the audit trail."""

    finding = models.ForeignKey(ReviewFinding, on_delete=models.CASCADE, related_name="responses")
    response = models.CharField(max_length=20, choices=ReviewFinding.Response.choices)
    note = models.TextField(max_length=1000, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class ReviewSession(models.Model):
    """Where the review of a task stands. Only a person completes it: the AI never marks work
    reviewed."""

    issue = models.OneToOneField("issues.Issue", on_delete=models.CASCADE, related_name="review_session")
    status = models.CharField(max_length=12, choices=[("in_progress", "In progress"), ("complete", "Complete")], default="in_progress")
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.TextField(max_length=1000, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class AssistantQuestion(models.Model):
    """A question a person asked the AI about a task, and its answer: what it said, how sure it
    was, and the passages it rests on. Kept, so the conversation and its sources can be checked."""

    class Status(models.TextChoices):
        PENDING = "pending", "Being answered"
        ANSWERED = "answered", "Answered"
        FAILED = "failed", "Failed"

    question_id = models.CharField(max_length=64, unique=True)
    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="assistant_questions")
    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    question = models.TextField(max_length=2000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    answer = models.TextField(blank=True)
    answer_status = models.CharField(max_length=12, blank=True)  # answered | partial | not_found
    sources = models.JSONField(default=list)  # [{id, label, how, evidence}]
    flags = models.JSONField(default=list)
    failure_reason = models.CharField(max_length=500, blank=True)
    cost_usd = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class AccountantAnswer(models.Model):
    """The accountant's answer to a pre-check question for the accountant (section B). Kept with
    the task and given to every later run, so a settled question is not asked again."""

    issue = models.ForeignKey("issues.Issue", on_delete=models.CASCADE, related_name="accountant_answers")
    question = models.TextField(max_length=1000)
    answer = models.TextField(max_length=2000)
    run = models.ForeignKey(AIPrecheck, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["answered_at", "id"]

