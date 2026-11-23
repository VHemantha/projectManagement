"""Local_Tax_AI's agents as LangGraph graphs (AFIT, 22 Nov 2026). Each is the same three steps:

    prepare -> ask -> check

prepare: the engagement (as TASKO's engine worked it out) and the request as the model's input - for a document,
         the document itself (read).
ask:     one Claude call through LangChain, the answer held to the agent's JSON schema.
check:   the answer validated with pydantic and cleaned: only keys the engagement has, nothing else kept.

Agents: chat, map_tb, analyse, reverse, return_prep (the draft return reviewed) and extract (a document read).
In demo mode (LOCAL_TAX_AI_LLM_MODE=fake) a stand-in answers from the engagement itself, so the workflow and the
tests run without Claude.
"""
import json
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import documents, prompts, schemas
from .llm import ask

MAX_CONTEXT = 60000


class State(TypedDict, total=False):
    agent: str
    request: dict
    content: Any
    raw: dict
    result: dict


def _context_text(ctx: dict) -> str:
    text = json.dumps(ctx, default=str, ensure_ascii=False)
    return text[:MAX_CONTEXT] + (" …(cut)" if len(text) > MAX_CONTEXT else "")


AGENTS = {
    "chat": (prompts.CHAT, schemas.CHAT, schemas.Chat),
    "map_tb": (prompts.MAP_TB, schemas.MAP_TB, schemas.MapTb),
    "analyse": (prompts.ANALYSE, schemas.ITEMS, schemas.Items),
    "reverse": (prompts.REVERSE, schemas.ITEMS, schemas.Items),
    "return_prep": (prompts.RETURN, schemas.ITEMS, schemas.Items),
    "extract": (prompts.EXTRACT, schemas.EXTRACT, schemas.Extract),
    "policies": (prompts.POLICIES, schemas.POLICIES, schemas.Policies),
    "rule_check": (prompts.RULE_CHECK, schemas.RULE_CHECK, schemas.RuleCheck),
    "prefill": (prompts.PREFILL, schemas.PREFILL, schemas.Prefill),
}


def prepare(state: State) -> State:
    r = state["request"]
    ctx = "ENGAGEMENT (worked out by TASKO's engine):\n" + _context_text(r.get("context") or {})
    if state["agent"] == "chat":
        history = "\n".join(f"{m.get('role')}: {m.get('text')}" for m in r.get("history") or [])
        content = f"{ctx}\n\nCONVERSATION SO FAR:\n{history or '(none)'}\n\nQUESTION:\n{r.get('question', '')}"
    elif state["agent"] == "extract":
        import base64

        data = base64.b64decode(r.get("content_b64") or "")
        content = documents.blocks(r.get("name") or "document", data) + [
            {"type": "text", "text": f"{ctx}\n\nRead the document above ({r.get('name')}); the accountant says it is: {r.get('kind') or 'auto'}."}]
    elif state["agent"] == "prefill":
        import base64

        data = base64.b64decode(r.get("content_b64") or "")
        content = documents.blocks(r.get("name") or "document", data) + [
            {"type": "text", "text": f"{ctx}\n\nRead the document above ({r.get('name')}) for the client info."}]
    elif state["agent"] == "rule_check":
        import base64

        data = base64.b64decode(r.get("content_b64") or "")
        content = documents.blocks(r.get("name") or "document", data) + [
            {"type": "text", "text": "REQUEST (the rule to check):\n" + json.dumps(r.get("rule") or {}, default=str, ensure_ascii=False)}]
    elif state["agent"] == "policies":
        content = f"{ctx}\n\nREQUEST (the standard policies):\n" + json.dumps(r.get("policies") or [], ensure_ascii=False)
    else:
        content = f"{ctx}\n\nREQUEST:\n{r.get('request') or '(review the engagement)'}"
    return {"content": content}


def call(state: State) -> State:
    system, schema, _ = AGENTS[state["agent"]]
    return {"raw": ask(system, state["content"], schema, reader=state["agent"] in ("extract", "rule_check", "prefill"),
                       fake=lambda content: demo(state["agent"], state["request"], content))}


def check(state: State) -> State:
    _, _, model = AGENTS[state["agent"]]
    parsed = model.model_validate(state.get("raw") or {})
    out = parsed.model_dump()
    ctx = state["request"].get("context") or {}
    levers = {lv.get("key") for lv in ctx.get("levers") or []}
    if state["agent"] == "chat":
        wi = out.get("what_if") or {}
        if not wi.get("lever") or wi.get("lever") not in levers or not re.fullmatch(r"-?\d+(\.\d+)?", str(wi.get("proposed", "")).replace(",", "")):
            out["what_if"] = None
        else:
            out["what_if"] = {"lever": wi["lever"], "proposed": str(wi["proposed"]).replace(",", "")}
    if state["agent"] in ("analyse", "reverse", "return_prep"):
        for item in out["items"]:
            if item.get("lever") not in levers:
                item["lever"] = ""
    if state["agent"] == "map_tb":
        headings = set((ctx.get("headings") or {}).keys())
        codes = {str(ln.get("code")) for ln in ((ctx.get("financials") or {}).get("tb") or [])}
        out["suggestions"] = [s for s in out["suggestions"] if s["heading"] in headings and s["code"] in codes]
    if state["agent"] == "extract":
        for ln in out["lines"]:
            for k in ("amount", "comparative"):
                v = str(ln.get(k) or "").replace(",", "").replace(" ", "")
                if v.startswith("(") and v.endswith(")"):
                    v = "-" + v[1:-1]
                ln[k] = v if re.fullmatch(r"-?\d+(\.\d+)?", v) else ""
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ln.get("date") or ""):
                ln["date"] = ""
            if out["kind"] == "fixed_assets" and ln.get("category") not in set(ctx.get("asset_classes") or []):
                ln["category"] = ""
            if out["kind"] == "prior_return" and ln.get("category") not in PRIOR_CATEGORIES:
                ln["category"] = "other"
        if not re.fullmatch(r"\d{4}/\d{2}", out.get("year_of_assessment") or ""):
            out["year_of_assessment"] = ""
    if state["agent"] == "prefill":
        out["fields"] = [f for f in out["fields"] if f["field"] in schemas.FIELDS and str(f["value"]).strip()]
        for f in out["fields"]:
            f["value"] = " ".join(str(f["value"]).split())[:500]
            if f["field"] == "fy_end" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f["value"]):
                f["value"] = ""
            if f["field"] == "entity_type" and f["value"] not in ("company", "partnership", "individual"):
                f["value"] = ""
        out["fields"] = [f for f in out["fields"] if f["value"]]
        lines = []
        for ln in out["lines"]:
            if ln["list"] not in schemas.LISTS:
                continue
            for k in ("amount", "comparative"):
                ln[k] = _number(ln.get(k))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ln.get("date") or ""):
                ln["date"] = ""
            if ln["amount"] or ln["list"] == "trial_balance" and ln["comparative"]:
                lines.append(ln)
        out["lines"] = lines
        balances = []
        for b in out["balances"]:
            b["balance"] = _number(b.get("balance"))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", b.get("date") or ""):
                b["date"] = ""
            if b["balance"]:
                balances.append(b)
        out["balances"] = balances
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", out.get("period_end") or ""):
            out["period_end"] = ""
        out["flags"] = [f for f in out["flags"] if f["kind"] in ("missing", "unclear", "inconsistent") and f["text"].strip()]
    if state["agent"] == "policies":
        wanted = {p.get("key") for p in (state["request"].get("policies") or [])}
        out["policies"] = [p for p in out["policies"] if p["key"] in wanted]
    return {"result": out}


def _number(v) -> str:
    """A printed amount as a plain number: "(1,200.50)" -> "-1200.50"; anything else -> ""."""
    s = str(v or "").replace(",", "").replace(" ", "").replace("Rs.", "").replace("LKR", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return s if re.fullmatch(r"-?\d+(\.\d+)?", s) else ""


PRIOR_CATEGORIES = {"revenue", "pbt", "taxable_income", "income_tax", "tax_payable", "losses_cf", "capital_allowances", "other"}


@lru_cache
def graph():
    g = StateGraph(State)
    g.add_node("prepare", prepare)
    g.add_node("ask", call)
    g.add_node("check", check)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "ask")
    g.add_edge("ask", "check")
    g.add_edge("check", END)
    return g.compile()


def run(agent: str, request: dict) -> dict:
    if agent not in AGENTS:
        raise KeyError(agent)
    return graph().invoke({"agent": agent, "request": request})["result"]


# --- the demo stand-in ----------------------------------------------------------------------------------------

def demo(agent: str, request: dict, content) -> dict:
    """What the demo answers: built from the engagement only, labelled as a demo, never a figure of its own."""
    ctx = request.get("context") or {}
    comp = ctx.get("computation") or {}
    if agent == "chat":
        q = str(request.get("question") or "")
        wi = {"lever": "", "proposed": ""}
        m = re.search(r"(?:by|of)\s*(?:rs\.?|lkr)?\s*([\d,]+)", q, re.I)
        if m and "what if" in q.lower():
            words = [w for w in re.findall(r"[a-z]{4,}", q.lower()) if w not in ("what", "change", "changes", "expenses", "income")]
            lever = next((lv for lv in ctx.get("levers") or [] if any(w in str(lv.get("label", "")).lower() for w in words)), None)
            if lever:
                change = float(m.group(1).replace(",", ""))
                sign = -1 if re.search(r"\b(fall|decrease|reduce|less|lower)", q, re.I) else 1
                wi = {"lever": lever["key"], "proposed": str(float(lever.get("amount") or 0) + sign * change)}
        return {"answer": f"(Demo) The engine's calculated tax payable is {comp.get('payable')}. Ask Local_Tax_AI with Claude switched on for an "
                          "explanation.", "points": ["Demo mode: no AI reading."], "uncertain": True, "what_if": wi}
    if agent == "map_tb":
        tb = ((ctx.get("financials") or {}).get("tb")) or []
        return {"suggestions": [{"code": ln["code"], "heading": "admin_expenses", "reason": "(Demo) unmapped expense"}
                                for ln in tb if not ln.get("heading") and float(ln.get("amount") or 0) > 0], "notes": []}
    if agent == "reverse":
        rev = ctx.get("reverse") or {}
        return {"summary": "(Demo) The engine's scenarios show the lines that alone could explain the difference.",
                "questions": [f"The client's expected tax is {rev.get('expected')}, but the calculated tax is {rev.get('calculated')}. Which income, "
                              "expense, relief or tax-credit line should we review to explain the difference?"],
                "items": [{"title": s.get("label", ""), "text": "(Demo) Review this line and its evidence.", "reference": "", "lever": s.get("key", ""),
                           "severity": "medium", "needs_review": True} for s in (rev.get("scenarios") or []) if s.get("feasible")][:5]}
    if agent in ("analyse", "return_prep"):
        return {"summary": "(Demo) Review the alerts below.", "questions": [],
                "items": [{"title": a.get("text", "")[:80], "text": a.get("text", ""), "reference": "", "lever": "", "severity": "medium",
                           "needs_review": True} for a in (ctx.get("alerts") or [])][:10]}
    if agent == "policies":
        return {"policies": [{"key": p.get("key", ""), "title": p.get("title", ""), "text": "(Demo) " + p.get("text", "")}
                             for p in request.get("policies") or []], "notes": ["Demo mode: the policies were not tailored."]}
    if agent == "prefill":
        name = str(request.get("name") or "")
        return {"kind": "other", "summary": f"(Demo) {name} was not read: switch Claude on to pre-fill from documents.", "period_end": "",
                "fields": [], "lines": [], "balances": [], "flags": [{"kind": "unclear", "text": "Demo mode: the document was not read.", "cite": ""}]}
    if agent == "rule_check":
        return {"agrees": "unclear", "value_in_document": "", "quote": "", "cite": "", "note": "(Demo) The document was not read."}
    return {"kind": "other", "summary": "(Demo) Documents are read with Claude switched on.", "gaps": ["Demo mode: the document was not read."],
            "year_of_assessment": "", "lines": []}
