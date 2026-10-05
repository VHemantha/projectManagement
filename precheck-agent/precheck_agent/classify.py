"""Decide what kind of document a file is, in code (file name first, then its first lines).
The class decides which checks apply to a file and which key document it can be (this year's
questionnaire, last year's statements or workpapers)."""
import re

DOCUMENT_CLASSES = [
    "trial_balance",
    "general_ledger",
    "bank",
    "reconciliation",
    "financial_statements",
    "prior_year_statements",
    "tax_computation",
    "tax_return",
    "tax_correspondence",
    "schedule",
    "questionnaire",
    "job_instructions",
    "workpaper",
    "correspondence",
    "other_evidence",
    "other",
]

# Ordered: the first pattern that matches the file name wins.
_NAME_RULES = [
    # First: a questionnaire is named for its purpose, whatever topics it covers (GST, rental…).
    (r"questionnaire|\bcq\b|checklist|client (information|details)|information (sheet|form)", "questionnaire", None),
    (r"\bgst\b|\bvat\b|\bbas\b", "tax_return", None),
    (r"\bir\s?3\b|\bir\s?4\b|\bir\s?10\b|\binc\b.*tax|income tax|tax summar|\bpir\b|student loan|\blcf\b|loss(es)? carried|provisional tax|terminal tax|\bsoe\b|statement of earnings|\bpayday\b|\bpaye\b|\bfbt\b|\brwt\b|withholding", "tax_computation", None),
    (r"\bfa\b.*\brecon|fixed asset|asset register|depreciation schedule", "schedule", None),
    (r"\bgl\s?review|ledger review|review notes|review points", "workpaper", None),
    (r"\b\d\s?year trend|trend analysis|comparison", "workpaper", None),
    (r"info(rmation)?\s?request|document request|\bletter of engagement|terms of engagement|\bloe\b|engagement", "job_instructions", None),
    (r"bank balance|bank confirmation|bank statement|\btransactions\b|\d{2}-\d{4}-\d{7}-\d{2,3}", "bank", None),
    (r"prior[\s_-]*year|\bpy\b|last[\s_-]*year|comparative", "prior_year_statements", r"statement|accounts|fs\b|financial"),
    (r"trial[\s_-]*balance|\btb\b", "trial_balance", None),
    (r"general[\s_-]*ledger|\bgl\b|nominal", "general_ledger", None),
    (r"reconcil|\brec\b|\brecon\b", "reconciliation", None),
    (r"bank|statement of account", "bank", None),
    (r"tax[\s_-]*comp|computation|capital allowance", "tax_computation", None),
    (r"tax[\s_-]*return|ct600|sa100|form\s*11|\bvat return", "tax_return", None),
    (r"hmrc|revenue|tax.*(letter|correspond|notice)", "tax_correspondence", None),
    (r"financial[\s_-]*statement|statutory accounts|annual accounts|draft accounts|\bfs\b|profit (and|&) loss|balance sheet", "financial_statements", None),
    (r"instruction|engagement|direction|planning memo|job brief", "job_instructions", None),
    (r"schedule|lead[\s_-]*sheet|fixed asset|debtors|creditors|accrual|prepayment|payroll|stock|inventory", "schedule", None),
    (r"workpaper|working|\bwp\b|lock dates|job[\s_-]*activity", "workpaper", None),
    (r"invoice|receipt|donation|mileage|expense claim|loan statement|settlement|sale and purchase|property manager|rates notice|insurance", "other_evidence", None),
]

_CONTENT_RULES = [
    (r"trial balance", "trial_balance"),
    (r"general ledger", "general_ledger"),
    (r"statement of (profit|financial position)|profit and loss|balance sheet", "financial_statements"),
    (r"\bdebit\b.*\bcredit\b", "trial_balance"),
    (r"balance per bank|reconciling items|unpresented|outstanding lodg", "reconciliation"),
    (r"profit and loss|statement of financial position|balance sheet|notes to the (financial )?statements", "financial_statements"),
    (r"taxable (total )?profits?|tax adjusted|corporation tax (payable|computation)", "tax_computation"),
]


def classify_email(name: str, sample_text: str = "") -> str:
    """An email is correspondence whatever its subject says: "RE: trial balance" is a message
    about the trial balance, not the trial balance, and must not satisfy a rule that looks for
    one. Letters to or from the tax authority keep their own class."""
    return "tax_correspondence" if classify(name, sample_text) in ("tax_correspondence", "tax_return") else "correspondence"


def classify(name: str, sample_text: str = "") -> str:
    lowered = re.sub(r"[_\-.]+", " ", name.lower())
    for pattern, cls, also in _NAME_RULES:
        if re.search(pattern, lowered) and (also is None or re.search(also, lowered)):
            return cls
    head = sample_text.lower()[:3000]
    for pattern, cls in _CONTENT_RULES:
        if re.search(pattern, head):
            return cls
    # A form of questions the client answered: many lines that end in a question mark.
    if sum(1 for line in sample_text.splitlines() if line.strip().endswith("?")) >= 6:
        return "questionnaire"
    return "other"
