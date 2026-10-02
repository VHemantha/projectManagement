"""Decide what kind of document a file is, in code (file name first, then its first lines).
The class picks which reader looks at it and which rules apply. See skills/gdrive-folder-reader
for the same table in words — keep the two in step."""
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
    "other",
]

READER_FOR_CLASS = {
    "trial_balance": "ledger_reader",
    "general_ledger": "ledger_reader",
    "bank": "ledger_reader",
    "reconciliation": "ledger_reader",
    "financial_statements": "statements_reader",
    "prior_year_statements": "statements_reader",
    "tax_computation": "tax_reader",
    "tax_return": "tax_reader",
    "tax_correspondence": "tax_reader",
    "schedule": "workpaper_reader",
    "questionnaire": "workpaper_reader",
    "job_instructions": "workpaper_reader",
    "workpaper": "workpaper_reader",
    "correspondence": "workpaper_reader",
    "other": "workpaper_reader",
}

READER_CLASSES: dict[str, list[str]] = {}
for _cls, _reader in READER_FOR_CLASS.items():
    READER_CLASSES.setdefault(_reader, []).append(_cls)
# An email, a photo or a file code could not place can be about anything: every reader may be
# shown it when it matches the question.
for _classes in READER_CLASSES.values():
    for _any in ("correspondence", "other"):
        if _any not in _classes:
            _classes.append(_any)

# Ordered: the first pattern that matches the file name wins.
_NAME_RULES = [
    (r"prior[\s_-]*year|\bpy\b|last[\s_-]*year|comparative", "prior_year_statements", r"statement|accounts|fs\b|financial"),
    (r"trial[\s_-]*balance|\btb\b", "trial_balance", None),
    (r"general[\s_-]*ledger|\bgl\b|nominal", "general_ledger", None),
    (r"reconcil|\brec\b", "reconciliation", None),
    (r"bank|statement of account", "bank", None),
    (r"tax[\s_-]*comp|computation|capital allowance", "tax_computation", None),
    (r"tax[\s_-]*return|ct600|sa100|form\s*11|\bvat return", "tax_return", None),
    (r"hmrc|revenue|tax.*(letter|correspond|notice)", "tax_correspondence", None),
    (r"financial[\s_-]*statement|statutory accounts|annual accounts|draft accounts|\bfs\b", "financial_statements", None),
    (r"questionnaire|checklist", "questionnaire", None),
    (r"instruction|engagement|direction|planning memo|job brief", "job_instructions", None),
    (r"schedule|lead[\s_-]*sheet|fixed asset|debtors|creditors|accrual|prepayment|payroll|stock|inventory", "schedule", None),
    (r"workpaper|working|\bwp\b", "workpaper", None),
]

_CONTENT_RULES = [
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
    return "other"


# Words in a Direction Note item that point to a reader. Scored, not first-match.
_READER_WORDS = {
    "ledger_reader": r"trial balance|\btb\b|ledger|\bgl\b|bank|reconcil|cash|journal|posting|suspense|control account",
    "statements_reader": r"financial statements?|accounts|disclosure|note \d|comparativ|prior year|balance sheet|profit and loss|p&l|directors'? report|presentation",
    "tax_reader": r"\btax\b|corporation tax|vat|paye|capital allowance|hmrc|revenue|deferred tax|return|ct600|computation",
    "workpaper_reader": r"workpaper|working paper|schedule|sign[\s-]?off|questionnaire|checklist|fixed asset|debtor|creditor|accrual|prepayment|payroll|stock|inventory|review point|lead sheet",
}


def reader_for_question(text: str) -> str | None:
    """The reader whose vocabulary the question uses most, or None when code cannot tell (the
    plan node then goes by the class of the best-matching document — still no model call)."""
    lowered = text.lower()
    scores = {reader: len(re.findall(pattern, lowered)) for reader, pattern in _READER_WORDS.items()}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] == 0 or (len(ranked) > 1 and ranked[0] == ranked[1]):
        return None
    return best
