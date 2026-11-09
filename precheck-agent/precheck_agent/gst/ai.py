"""Where the WP Agent uses the model: reading documents into records, telling what an unexplained
file is, mapping unusual column headings, telling import GST from duty and freight, and writing the
summary. Each call is given the skill it needs (gst-document-reading or nz-gst-reconciliation) and a
strict answer shape; the answer is data that code then checks. Every figure in the reconciliation
is computed by code, never by the model."""
import json
import logging

from langchain_core.messages import HumanMessage

from ..budget import usage_from_message
from ..config import get_settings
from ..llm import get_model, model_id, stop_reason, text_of
from ..prompting import system_message
from ..skills_loader import get_skill
from .sources import Source, full_text

logger = logging.getLogger(__name__)
READING, METHOD = "gst-document-reading", "nz-gst-reconciliation"
_STR, _NUM, _BOOL = {"type": "string"}, {"type": "number"}, {"type": "boolean"}


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _list(item: dict) -> dict:
    return {"type": "array", "items": _obj(item)}


# Amounts are strings, copied as the document shows them; code parses them.
SCHEMAS = {
    "gst_returns": _obj({"returns": _list({
        "period_start": _STR, "period_end": _STR, "version": _STR, "filed_date": _STR, "box5": _STR, "box6": _STR, "box8": _STR,
        "box9": _STR, "box10": _STR, "box11": _STR, "box12": _STR, "box13": _STR, "box14": _STR, "box15": _STR, "source": _STR, "note": _STR})}),
    "ird_statement": _obj({"lines": _list({
        "date": _STR, "effective_date": _STR, "type": _STR, "period_end": _STR, "debit": _STR, "credit": _STR, "reference": _STR,
        "description": _STR, "balance": _STR, "source": _STR}), "closing_balance": _STR, "statement_to": _STR}),
    "prior_year_recon": _obj({"balance_date": _STR, "gl_gst_balance": _STR, "ird_outstanding": _STR, "unpaid_returns": _list({
        "period_end": _STR, "amount": _STR, "source": _STR}), "timing_items": _list({"item": _STR, "amount": _STR, "source": _STR}),
        "unresolved": _list({"item": _STR, "amount": _STR, "source": _STR})}),
    "late_claims": _obj({"items": _list({
        "date": _STR, "reference": _STR, "contact": _STR, "description": _STR, "gst": _STR, "side": {"type": "string", "enum": ["output", "input", ""]},
        "return_period_end": _STR, "source": _STR})}),
    "ageing": _obj({"has_gst_column": _BOOL, "as_at": _STR, "rows": _list({
        "contact": _STR, "reference": _STR, "date": _STR, "total": _STR, "gst": _STR, "source": _STR}), "report_total": _STR, "report_gst_total": _STR}),
}
CLASSIFY = _obj({"items": _list({"sid": _STR, "kind": _STR, "why": _STR})})
MAPPING = _obj({"sheet": _STR, "header_row": {"type": "integer"}, "columns": _list({"field": _STR, "column": {"type": "integer"}})})
IMPORTS = _obj({"items": _list({"id": _STR, "component": {"type": "string", "enum": ["import_gst", "customs_duty", "freight", "brokerage", "other", "unclear"]},
                                 "why": _STR})})
SUMMARY = _obj({"summary": _STR})

ASK = {
    "gst_returns": "List every GST return period in the document, with each box as shown. One record per period and version.",
    "ird_statement": "List every line of the IRD GST account statement in order, with the GST period IRD allocated it to.",
    "prior_year_recon": ("Read last year's GST reconciliation: the GL balance it reconciled, the IRD balance, returns unpaid at its balance date, timing "
                         "items and unresolved items. Give GST payable to IRD as a positive amount and a refund due from IRD as a negative amount, "
                         "whatever sign the workpaper prints."),
    "late_claims": "List each transaction included in a later return that belongs to an earlier period (late claims and amendments).",
    "ageing": "Read the ageing report: one row per invoice (or per contact when only contacts are shown), with the GST column if the report has one.",
}


class Reader:
    """The run's model calls, with their usage and a cap on reading calls."""

    def __init__(self, run_id: str = ""):
        self.s = get_settings()
        self.run_id = run_id
        self.usage: list[dict] = []
        self.reading_calls = 0

    def _call(self, task: str, skill: str, body: str, schema: dict) -> dict:
        system = (f"You are AFIT Connect's WP Agent, preparing a New Zealand GST reconciliation workpaper for an accountant.\n\n"
                  f"# Skill: {skill}\n{get_skill(skill).body}")
        message = get_model("gst", self.s).invoke(
            [system_message("drafter", system, self.s), HumanMessage(content=body)],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        self.usage.append({"node": "gst", "task_id": task, "model": model_id("gst", self.s), "calls": 1, "run_id": self.run_id,
                           **usage_from_message(message)})
        if stop_reason(message) in ("refusal", "max_tokens"):
            raise ValueError(f"the model stopped early ({stop_reason(message)})")
        return json.loads(text_of(message) or "{}")

    def _reading(self) -> bool:
        self.reading_calls += 1
        return self.reading_calls <= self.s.gst_max_reading_calls

    def classify(self, sources: list[Source]) -> list[str]:
        from .classify import KINDS

        body = ("What is each document? Kinds: " + "; ".join(f"{k} = {v}" for k, v in KINDS.items()) + "\n\n"
                + "\n\n".join(f"== {s.sid}: {s.name} ==\n{full_text(s, limit=1500)}" for s in sources))
        try:
            answer = self._call("classify", READING, body, CLASSIFY) if self._reading() else {}
        except Exception:
            logger.exception("Classifying documents failed")
            answer = {}
        kinds = {str(i.get("sid")): str(i.get("kind")) for i in answer.get("items", [])}
        return [kinds.get(s.sid, "other") for s in sources]

    def extract(self, kind: str, src: Source) -> dict:
        """A document read into the records of its kind ({} when it could not be read)."""
        if not self._reading():
            return {}
        body = (f"{ASK[kind]}\nGive each record's source as its place in the document (the [page / sheet row] shown before each line).\n\n"
                f"== {src.sid}: {src.name} ==\n{full_text(src)}")
        try:
            return self._call(f"read_{kind}", READING, body, SCHEMAS[kind])
        except Exception:
            logger.exception("Reading %s (%s) failed", src.name, kind)
            return {}

    def map_columns(self, kind: str, fields: dict[str, str], src: Source) -> dict:
        """Which row holds the headings and which column holds each field, for a table code could not map."""
        if not self._reading():
            return {}
        body = (f"This is a {kind.replace('_', ' ')}. Find the heading row and the column (counting from 0) of each field. Fields: "
                + "; ".join(f"{k} = {v}" for k, v in fields.items()) + ". Leave out a field the table doesn't have.\n\n" + full_text(src, limit=6000))
        try:
            return self._call(f"map_{kind}", READING, body, MAPPING)
        except Exception:
            logger.exception("Mapping the columns of %s failed", src.name)
            return {}

    def classify_imports(self, lines: list[dict]) -> dict[str, dict]:
        """{line id: {"component", "why"}} for GL lines that mention import GST, Customs or similar."""
        if not lines or not self._reading():
            return {}
        body = ("For each general ledger line, say whether the amount is import GST (GST collected by Customs on imported goods), customs duty, "
                "freight, brokerage, something else, or unclear from the line.\n\n"
                + "\n".join(f"{x['id']}: account {x['account']}; {x['date']}; {x['description']}; ref {x['ref']}; amount {x['amount']}" for x in lines))
        try:
            answer = self._call("import_gst", METHOD, body, IMPORTS)
        except Exception:
            logger.exception("Classifying import GST lines failed")
            return {}
        return {str(i.get("id")): {"component": i.get("component", "unclear"), "why": str(i.get("why", ""))[:300]} for i in answer.get("items", [])}

    def summary(self, facts: str) -> str:
        try:
            answer = self._call("summary", METHOD, "Write the summary (3 to 6 sentences) from these results. Use only these figures.\n\n" + facts, SUMMARY)
        except Exception:
            logger.exception("Writing the WP Agent summary failed")
            return ""
        return " ".join(str(answer.get("summary", "")).split())[:1500]
