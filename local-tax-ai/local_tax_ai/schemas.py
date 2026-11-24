"""The answer shapes of Local_Tax_AI's agents (AFIT, 22 Nov 2026). Each is given to Claude as a JSON schema (the
API keeps the answer to it) and checked again with pydantic before it leaves the service. None carries a figure
the engine works out: suggestions, explanations, questions, citations - and, for a "what if", only the line and
the amount the person asked about."""
from pydantic import BaseModel, Field

_S = {"type": "string"}


def obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def arr(item: dict) -> dict:
    return {"type": "array", "items": item}


# --- chat ---------------------------------------------------------------------------------------------------
CHAT = obj({"answer": _S, "points": arr(_S), "uncertain": {"type": "boolean"},
            "what_if": obj({"lever": _S, "proposed": _S})})


class WhatIf(BaseModel):
    lever: str = ""
    proposed: str = ""


class Chat(BaseModel):
    answer: str
    points: list[str] = Field(default_factory=list, max_length=8)
    uncertain: bool = False
    what_if: WhatIf | None = None


# --- TB mapping ----------------------------------------------------------------------------------------------
MAP_TB = obj({"suggestions": arr(obj({"code": _S, "heading": _S, "reason": _S})), "notes": arr(_S)})


class Suggestion(BaseModel):
    code: str
    heading: str
    reason: str = ""


class MapTb(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- analysis, reverse tax and return review ------------------------------------------------------------------
ITEMS = obj({"summary": _S, "questions": arr(_S),
             "items": arr(obj({"title": _S, "text": _S, "reference": _S, "lever": _S, "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                               "needs_review": {"type": "boolean"}}))})


class Item(BaseModel):
    title: str
    text: str
    reference: str = ""
    lever: str = ""
    severity: str = "medium"
    needs_review: bool = True


class Items(BaseModel):
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)


# --- document extraction ----------------------------------------------------------------------------------------
KINDS = ["trial_balance", "general_ledger", "income", "payments", "prior_return", "fixed_assets", "prior_fs", "other"]
EXTRACT = obj({"kind": {"type": "string", "enum": KINDS}, "summary": _S, "gaps": arr(_S), "year_of_assessment": _S,
               "lines": arr(obj({"description": _S, "amount": _S, "category": _S, "code": _S, "comparative": _S, "date": _S, "cite": _S}))})


class Line(BaseModel):
    description: str
    amount: str = ""
    category: str = ""
    code: str = ""
    comparative: str = ""
    date: str = ""
    cite: str = ""


class Extract(BaseModel):
    kind: str = "other"
    year_of_assessment: str = ""
    summary: str = ""
    gaps: list[str] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)


# --- accounting policies tailored (Phase 3) ---------------------------------------------------------------------
POLICIES = obj({"policies": arr(obj({"key": _S, "title": _S, "text": _S})), "notes": arr(_S)})


class Policy(BaseModel):
    key: str
    title: str = ""
    text: str


class Policies(BaseModel):
    policies: list[Policy] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- a rule checked against a law document (Phase 4) ---------------------------------------------------------------
RULE_CHECK = obj({"agrees": {"type": "string", "enum": ["yes", "no", "unclear"]}, "value_in_document": _S, "quote": _S, "cite": _S,
                  "note": _S})


class RuleCheck(BaseModel):
    agrees: str = "unclear"
    value_in_document: str = ""
    quote: str = ""
    cite: str = ""
    note: str = ""


# --- pre-filling the client info from one supporting document --------------------------------------------------------
DOC_KINDS = ["trial_balance", "bank_statement", "bank_confirmation", "general_ledger", "financial_statements", "prior_return", "fixed_assets",
             "salary_certificate", "wht_certificate", "tax_payment", "invoice_or_receipt", "registration", "loan_statement", "other"]
FIELDS = ["legal_name", "tin", "nic_or_reg", "address", "activity", "fy_end", "entity_type"]
LISTS = ["income", "payments", "assets", "liabilities", "trial_balance"]
PREFILL = obj({
    "kind": {"type": "string", "enum": DOC_KINDS}, "summary": _S, "period_end": _S,
    "fields": arr(obj({"field": {"type": "string", "enum": FIELDS}, "value": _S, "cite": _S})),
    "lines": arr(obj({"list": {"type": "string", "enum": LISTS}, "category": _S, "description": _S, "amount": _S, "comparative": _S, "code": _S,
                      "date": _S, "cite": _S})),
    "balances": arr(obj({"bank": _S, "account": _S, "date": _S, "balance": _S, "cite": _S})),
    "flags": arr(obj({"kind": {"type": "string", "enum": ["missing", "unclear", "inconsistent"]}, "text": _S, "cite": _S})),
})


class PrefillField(BaseModel):
    field: str
    value: str = ""
    cite: str = ""


class PrefillLine(BaseModel):
    list: str
    category: str = ""
    description: str = ""
    amount: str = ""
    comparative: str = ""
    code: str = ""
    date: str = ""
    cite: str = ""


class Balance(BaseModel):
    bank: str = ""
    account: str = ""
    date: str = ""
    balance: str = ""
    cite: str = ""


class DocFlag(BaseModel):
    kind: str = "unclear"
    text: str
    cite: str = ""


class Prefill(BaseModel):
    kind: str = "other"
    summary: str = ""
    period_end: str = ""
    fields: list[PrefillField] = Field(default_factory=list)
    lines: list[PrefillLine] = Field(default_factory=list)
    balances: list[Balance] = Field(default_factory=list)
    flags: list[DocFlag] = Field(default_factory=list)


# --- a dummy trial balance from a story (AFIT, 24 Nov 2026) -------------------------------------------------------
TB_STORY = obj({"accounts": arr(obj({"code": _S, "name": _S, "heading": _S, "amount": _S, "comparative": _S})),
                "assumptions": arr(_S), "notes": arr(_S)})


class StoryAccount(BaseModel):
    code: str = ""
    name: str
    heading: str = ""
    amount: str = ""
    comparative: str = ""


class TbStory(BaseModel):
    accounts: list[StoryAccount] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- PPE accounts' categories (AFIT, 24 Nov 2026) ------------------------------------------------------------------
PPE_CLASSIFY = obj({"suggestions": arr(obj({"code": _S, "category": _S, "role": {"type": "string", "enum": ["cost", "accumulated"]}, "reason": _S})),
                    "notes": arr(_S)})


class PpeSuggestion(BaseModel):
    code: str
    category: str = ""
    role: str = "cost"
    reason: str = ""


class PpeClassify(BaseModel):
    suggestions: list[PpeSuggestion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
