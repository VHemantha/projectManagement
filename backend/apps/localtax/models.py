"""The Local Tax workflow's records (AFIT, 22 Nov 2026), for Team 3 > Local's cards only (clients.Client.workflow =
"local_tax"). One engagement per card: the questionnaire, the trial balance, the adjustments and the audit trail.
The figures are never stored as results: they are worked out by the engine (engine/) from these records each time,
so a correction anywhere flows through the financial statements, the computation and the draft return at once."""
from django.conf import settings
from django.db import models


class TaxEngagement(models.Model):
    class Entity(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        COMPANY = "company", "Company"
        PARTNERSHIP = "partnership", "Partnership"

    class Residency(models.TextChoices):
        RESIDENT = "resident", "Resident"
        NON_RESIDENT = "non_resident", "Non-resident"

    class Framework(models.TextChoices):
        FULL = "full", "Full LKAS/SLFRS"
        SMES = "smes", "SLFRS for SMEs"
        SMALLER = "smaller", "Sri Lanka Accounting Standard for Smaller Entities"

    class Basis(models.TextChoices):
        TOTAL = "total", "Total tax liability"
        REMAINING = "remaining", "Remaining payable after credits and instalments"

    STAGES = ("questionnaire", "fs", "computation", "return")
    STATUSES = ("not_started", "in_progress", "ready_for_review", "approved")

    issue = models.OneToOneField("issues.Issue", on_delete=models.CASCADE, related_name="tax_engagement")
    entity_type = models.CharField(max_length=12, choices=Entity.choices, default=Entity.COMPANY)
    residency = models.CharField(max_length=14, choices=Residency.choices, default=Residency.RESIDENT)
    year_of_assessment = models.CharField(max_length=9, default="2024/25")
    fy_end = models.DateField(null=True, blank=True)
    tax_type = models.CharField(max_length=4, default="CIT")  # CIT, IIT or PIT (partnership); VAT, SSCL, APIT later
    legal_name = models.CharField(max_length=200, blank=True)
    client_name = models.CharField(max_length=200, blank=True)
    tin = models.CharField(max_length=30, blank=True)
    nic_or_reg = models.CharField(max_length=40, blank=True)
    address = models.TextField(max_length=500, blank=True)
    activity = models.TextField(max_length=1000, blank=True)
    reporting_framework = models.CharField(max_length=8, choices=Framework.choices, default=Framework.SMES)
    audited = models.BooleanField(default=True)
    expected_tax = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    expected_basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.TOTAL)
    # The questionnaire's lists, validated on the way in (serializers.py): income (with expenses and foreign
    # details), assets, liabilities, payments, qualifying_payments, losses_bf, and the computation's own lines
    # (add_backs, deductions, capital_allowances, special_income, pbt_manual), and the return's overrides.
    data = models.JSONField(default=dict, blank=True)
    # {stage: {"status", "by", "at"}}
    stages = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def stage(self, key: str) -> dict:
        return (self.stages or {}).get(key) or {"status": "not_started"}


class TbLine(models.Model):
    """One trial balance account: debit-positive current-year and comparative amounts, and the FS heading it is
    mapped to - set by rule, suggested by the AI, or chosen by a person."""

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="tb_lines")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    comparative = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    heading = models.CharField(max_length=40, blank=True)
    heading_by = models.CharField(max_length=8, default="rule")  # rule | ai | person
    heading_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["code", "id"]
        unique_together = [("engagement", "code")]


class Adjustment(models.Model):
    """A journal, a reclassification, a tax adjustment or a correction from the reverse tax analysis. Kept with
    its original and proposed amounts, reason and evidence; only an approved one reaches the figures. An
    accounting one moves trial balance accounts (its lines net to nil); a tax-only one changes a line of the
    computation and leaves the accounting profit as it is."""

    class Kind(models.TextChoices):
        JOURNAL = "journal", "Journal"
        RECLASS = "reclass", "Reclassification"
        TAX = "tax", "Tax adjustment"
        REVERSE = "reverse", "Reverse tax correction"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="adjustments")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    scope = models.CharField(max_length=10, default="accounting")  # accounting | tax
    target = models.CharField(max_length=80, blank=True)  # a computation line ("add_backs:3") or a TB account code
    label = models.CharField(max_length=200)
    original = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    proposed = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    lines = models.JSONField(default=list, blank=True)  # journal lines [{code, name, amount}] (debit +)
    reason = models.TextField(max_length=2000)
    evidence = models.ForeignKey("issues.Attachment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    evidence_note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    history = models.JSONField(default=list, blank=True)  # earlier versions of the proposal
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)
    # The journal register (AFIT, 24 Nov 2026): each journal's reference (JE-001, ...; JE-DEP for the depreciation journal),
    # its date, and the journal it reverses (an approved journal is never edited or deleted: it is reversed).
    ref = models.CharField(max_length=20, blank=True)
    entry_date = models.DateField(null=True, blank=True)
    reverses = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reversals")

    class Meta:
        ordering = ["-created_at", "-id"]


class Extraction(models.Model):
    """What the AI read from an uploaded document (TB, GL, prior computation...): lines citing the document, used
    only once a person confirms them."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="extractions")
    attachment = models.ForeignKey("issues.Attachment", null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=40)
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class EngagementEvent(models.Model):
    """The audit trail: every change by a person or the AI - what, from what, to what, why, who and when."""

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.CharField(max_length=20, default="person")  # person | ai | system
    action = models.CharField(max_length=60)
    detail = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]


class AiMessage(models.Model):
    """The engagement's conversation with Local_Tax_AI, kept so it carries on where it left off. A "what if"
    answer is marked hypothetical, with the engine's figures."""

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="ai_messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    role = models.CharField(max_length=10)  # person | ai
    text = models.TextField(max_length=6000)
    data = models.JSONField(default=dict, blank=True)  # points, sources, hypothetical figures
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]


class RuleReview(models.Model):
    """A tax professional's review of one rule of a year of assessment (Phase 4): validated as it is in the rules
    file, or corrected to another value, with the legal reference relied on. Only a reviewed rule counts as
    validated; every review (and each one it replaced) is kept."""

    class Status(models.TextChoices):
        VALIDATED = "validated", "Validated"
        CORRECTED = "corrected", "Corrected"

    year_of_assessment = models.CharField(max_length=9)
    rule = models.CharField(max_length=120)  # "company.standard_rate"
    status = models.CharField(max_length=10, choices=Status.choices)
    value = models.JSONField(null=True, blank=True)  # the corrected value (the file's value for a validation)
    file_value = models.JSONField(null=True, blank=True)  # the file's value when reviewed
    ref = models.CharField(max_length=500)
    note = models.TextField(max_length=2000, blank=True)
    active = models.BooleanField(default=True)  # False once replaced by a later review or withdrawn
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["year_of_assessment", "rule", "active"])]


class ReturnFieldReview(models.Model):
    """A field of the draft return checked against the year's return in RAMIS (Phase 4): the official cage/field
    reference for TASKO's placeholder code, for companies or individuals."""

    year_of_assessment = models.CharField(max_length=9)
    entity_type = models.CharField(max_length=12)
    code = models.CharField(max_length=10)
    official = models.CharField(max_length=60)  # the RAMIS cage / field number
    note = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]


class SourceDocument(models.Model):
    """A Local client's supporting document (AFIT): uploaded to the task or copied from the client's shared Google
    Drive folder, and what Local_Tax_AI made of it when it read it for the client info."""

    class Origin(models.TextChoices):
        UPLOAD = "upload", "Uploaded"
        DRIVE = "drive", "Google Drive"

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="documents")
    attachment = models.ForeignKey("issues.Attachment", on_delete=models.CASCADE, related_name="+")
    origin = models.CharField(max_length=8, choices=Origin.choices, default=Origin.UPLOAD)
    drive_file_id = models.CharField(max_length=200, blank=True)
    drive_version = models.CharField(max_length=100, blank=True)
    drive_path = models.CharField(max_length=500, blank=True)
    drive_url = models.CharField(max_length=1000, blank=True)
    kind = models.CharField(max_length=30, blank=True)  # what the AI found it is (bank_statement, trial_balance...)
    summary = models.CharField(max_length=500, blank=True)
    period_end = models.DateField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)  # last read for the client info (null: not yet)
    read_error = models.CharField(max_length=500, blank=True)
    reading = models.JSONField(default=dict, blank=True)  # Local_Tax_AI's checked reading, kept so a document is read once per version
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Suggestion(models.Model):
    """A value Local_Tax_AI found in the documents for the client info, with where it came from. Used only once the
    accountant confirms it (as it is, or edited); then it flows into the financial statements and computation."""

    class Status(models.TextChoices):
        PENDING = "pending", "To verify"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Replaced by a later reading"

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="suggestions")
    run = models.CharField(max_length=40)
    # "field:legal_name" | "income" | "payments" | "assets" | "liabilities" | "trial_balance" | "bank_balance"
    target = models.CharField(max_length=40)
    value = models.JSONField()
    sources = models.JSONField(default=list)  # [{"document", "attachment_id", "cite"}]
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    edited = models.BooleanField(default=False)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Flag(models.Model):
    """Something in the documents the accountant must resolve: missing, unclear, or inconsistent across documents
    (or with the client info), with the documents concerned."""

    class Kind(models.TextChoices):
        MISSING = "missing", "Missing"
        UNCLEAR = "unclear", "Unclear"
        INCONSISTENT = "inconsistent", "Inconsistent"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        SUPERSEDED = "superseded", "Replaced by a later reading"

    engagement = models.ForeignKey(TaxEngagement, on_delete=models.CASCADE, related_name="flags")
    run = models.CharField(max_length=40)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    target = models.CharField(max_length=40, blank=True)
    text = models.CharField(max_length=1000)
    sources = models.JSONField(default=list)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=1000, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class ClientPolicy(models.Model):
    """A Local client's own accounting policies, kept with the client (the sub-workspace) so they carry into every later
    year's card (AFIT, 24 Nov 2026): the depreciation policy - per asset category, its method, annual rate and residual
    value - used by the depreciation schedule of each year's engagement."""

    client = models.OneToOneField("clients.Client", on_delete=models.CASCADE, related_name="local_tax_policy")
    depreciation = models.JSONField(default=list, blank=True)  # [{key, label, method, rate, residual}]
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
