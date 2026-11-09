"""What each document is. The file name and its headings decide when they say it plainly; the model
is asked only for a file neither explains (gst-document-reading skill). An ageing report the
accountant gave in its own field keeps that role."""
import re

from .sources import Source, full_text

KINDS = {
    "ar_ageing": "Accounts receivable ageing report (year end)",
    "ap_ageing": "Accounts payable ageing report (year end)",
    "general_ledger": "General ledger (full year)",
    "trial_balance": "Trial balance (year end)",
    "journal_report": "Journal report / audit history",
    "gst_returns": "GST return summary (GST101A)",
    "ird_statement": "IRD GST account statement",
    "late_claims": "Later returns' transaction detail / late claims",
    "prior_year_recon": "Prior-year GST reconciliation",
    "xero_gst_recon": "Xero GST reconciliation report",
    "customs": "Customs / broker / import documents",
    "invoice": "Invoice or supporting document",
    "bank": "Bank statement or bank evidence",
    "other": "Other / not used",
}

# (kind, pattern on the lower-case file name or its first lines), most specific first.
_RULES = [
    ("ar_ageing", r"aged\s*(receivable|debtor)|receivables?\s*ageing|debtors?\s*ageing|ar\s*ageing"),
    ("ap_ageing", r"aged\s*(payable|creditor)|payables?\s*ageing|creditors?\s*ageing|ap\s*ageing"),
    ("prior_year_recon", r"((prior|previous|last)\s*(year|yr)|\bpy\b).*gst|gst.*((prior|previous|last)\s*(year|yr)|\bpy\b)"),
    ("late_claims", r"late\s*claim|transactions?\s*by\s*return|gst\s*audit|subsequent\s*(gst\s*)?return|gst\s*return\s*detail|filed\s*period"),
    ("xero_gst_recon", r"gst\s*reconciliation\s*report|gst\s*reconciliation\s*\(xero\)"),
    # IRD's myIR "GST Transaction Summary Report" is the GST account statement (AFIT, 9 Nov 2026).
    ("ird_statement", r"transaction\s*summary|(ird|inland\s*revenue|myir).*(statement|account\s*activity|transactions?)|"
                      r"gst\s*(account\s*)?statement|account\s*activity"),
    ("gst_returns", r"gst\s*returns?|return\s*summary|gst\s*101|gst101|returns?\s*filed"),
    ("journal_report", r"journal\s*report|manual\s*journals?|journals?\s*(listing|audit)|audit\s*(history|trail)|history\s*and\s*notes"),
    ("general_ledger", r"general\s*ledger|\bgl\b|ledger\s*detail|account\s*transactions"),
    ("trial_balance", r"trial\s*balance|\btb\b"),
    ("customs", r"customs|nzcs|import\s*(entry|gst)|broker|clearance"),
    ("bank", r"bank\s*statement|bank\s*rec"),
    ("invoice", r"invoice|bill\b|receipt"),
]


def by_rules(src: Source) -> str | None:
    name = re.sub(r"[_\-.]+", " ", src.name.lower())
    for kind, pattern in _RULES:
        if re.search(pattern, name):
            return kind
    head = full_text(src, limit=1500).lower()
    for kind, pattern in _RULES:
        if re.search(pattern, head):
            return kind
    return None


def classify(sources: list[Source], ai=None) -> None:
    """Sets each source's kind and how it was decided."""
    unknown = []
    for src in sources:
        if src.role:
            src.kind, src.kind_how = src.role, "accountant"
        elif src.error:
            src.kind, src.kind_how = "other", "unreadable"
        elif kind := by_rules(src):
            src.kind, src.kind_how = kind, "name"
        else:
            unknown.append(src)
    if unknown and ai is not None:
        for src, kind in zip(unknown, ai.classify(unknown)):
            src.kind, src.kind_how = (kind, "ai") if kind in KINDS else ("other", "ai")
    for src in unknown:
        if not src.kind_how:
            src.kind, src.kind_how = "other", "unknown"
