"""Model access. Claude only, model ids from config: Opus does the professional pre-check,
Sonnet drafts a Direction Note, Haiku writes out images.

`llm_mode = "fake"` swaps in scripted models with the same interface. Tests use them to drive
the real graph and agents without a key, and the demo mode uses them so the screen can be shown
before credentials exist. Fake output is labelled as such in every result.
"""
import json
import re
from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .config import Settings, family, get_settings
from .textutil import est_tokens

Responder = Callable[[list[BaseMessage], dict], AIMessage]


class ScriptedChatModel(BaseChatModel):
    """A chat model whose replies come from a Python function. Counts its calls."""

    responder: Any
    name_: str = "fake-model"
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # tools are ignored: scripted replies are final
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        reply = self.responder(messages, kwargs)
        self.calls.append({"messages": messages, "kwargs": kwargs, "reply": reply})
        return ChatResult(generations=[ChatGeneration(message=reply)])


# --- default fake behaviour (demo mode) -----------------------------------------------------

def _usage(prompt_text: str, reply_text: str) -> dict:
    i, o = est_tokens(prompt_text), est_tokens(reply_text)
    return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}


def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block["text"])
        elif block.get("type") == "document":
            parts.extend(b["text"] for b in block["source"]["content"])
    return "\n".join(parts)


def demo_drafter(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    """Stand-in for the drafting model: accepted past findings and current flags become items,
    then the standard list for the kinds of document present."""
    from .directions import standard_items

    payload = json.loads(_flatten(messages[-1].content).split("INPUT:", 1)[1])
    items = []
    for f in payload["history"]["past_findings"]:
        if f.get("decision") == "accepted":
            items.append({"text": f"Confirm this is fixed: {f['title']}", "reason": "A reviewer accepted this finding on an earlier job.", "basis": "history"})
    for c in payload["checks"]:
        items.append({"text": f"Resolve or explain: {c['result']}", "reason": "The automatic checks flagged this now.", "basis": "current"})
    kinds = {d["kind"].replace(" ", "_") for d in payload["documents"]}
    items += standard_items(kinds)
    text = json.dumps({"items": items})
    return AIMessage(content=text, usage_metadata=_usage(_flatten(messages[-1].content), text))


def demo_vision(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    """Demo mode cannot see: it says so, and the file is reported as needing a person."""
    text = "Shows: an image (demo mode has no model, so the image was not read)"
    return AIMessage(content=text, usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})


def demo_guide(body: str, by) -> AIMessage:
    """Stand-in for the guide (demo mode and tests): the eight sections, with the first bank payee
    raised as a suspected event and followed through to the sequence, a query and the checklist."""
    banks, tb = by("B"), by("T")
    payees = [ln.split(" | ") for ln in body.splitlines() if re.match(r"^B\d+\.\d+ \| ", ln)]
    outstanding = [ln.split(" — ", 1)[-1] for ln in body.splitlines() if ln.startswith("Still requested from the client: ")]
    first = payees[0] if payees else None
    answer = {
        "snapshot": {"activities": "Demo client.", "assets_and_funding": "As in last year's accounts.",
                     "records": f"{len(banks)} bank export(s); last year's trial balance.", "bookkeeping": "Bank exports only.",
                     "period": "Year to 31 March.", "sources": [p[0] for p in banks[:1]] + [p[0] for p in tb[:1]]},
        "events": [{"id": "E1", "event": f"Payments to {first[1]}.", "status": "suspected", "why_it_matters": "May be a significant transaction.",
                    "action": "Confirm what the payments were for.", "effect": "Not yet quantifiable.", "sources": [first[0]]}] if first else [],
        "prior_year": [{"item": f"Closing balance: {p[1]}.", "kind": "balance", "follow_through": "Agree the opening balance.", "sources": [p[0]]}
                       for p in tb[:2]],
        "risks": [{"area": "Bank", "what_could_be_wrong": f"{p[1]} is not reconciled.", "examine": "The year-end balance.",
                   "evidence": "The bank statement.", "events": [], "sources": [p[0]]} for p in banks[:3]],
        "sequence": [{"step": f"Reconcile {p[1]} to its year-end balance.", "depends_on": "nothing", "can_start_now": True, "escalate": "",
                      "events": ["E1"] if first and i == 0 else [], "sources": [p[0]]} for i, p in enumerate(banks[:3])],
        "judgments": [],
        "queries": {"manager": [], "client": [{"question": "What were the payments to the first payee for?", "events": ["E1"] if first else [], "sources": []}],
                    "outstanding": [{"item": item, "events": [], "sources": []} for item in outstanding]},
        "checklist": [{"check": "Significant events resolved.", "status": "open", "events": ["E1"] if first else []},
                      {"check": "Bank accounts reconciled.", "status": "open", "events": []}],
    }
    text = json.dumps(answer)
    return AIMessage(content=text, usage_metadata=_usage(body, text))


def demo_precheck(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    """Stand-in for the pre-check model (demo mode and tests): the type from keywords in the
    questionnaire, each bank account already provided by its export, and last year's larger
    trial balance lines requested — enough to exercise the whole pipeline."""
    body = _flatten(messages[-1].content)
    lines = [ln for ln in body.splitlines() if re.match(r"^[A-Z]\d+(\.\d+)? \| ", ln)]
    by = lambda p: [ln.split(" | ") for ln in lines if re.match(rf"^{p}\d+ \| ", ln)]  # noqa: E731
    if "THIS YEAR'S DRAFT FINANCIAL STATEMENTS" in body:
        return demo_review(body, by)
    if "== THE LATEST PRE-CHECK'S RESULT ==" in body:
        return demo_guide(body, by)
    q_text = " ".join(" | ".join(parts[1:]) for parts in by("Q")).lower()
    btype = "residential_rental" if re.search(r"rent|tenant|property manager", q_text) else ("investment" if re.search(r"dividend|shares|fund", q_text) else "general")
    q_ids = [parts[0] for parts in by("Q")][:2]
    items = []
    for parts in by("B"):
        items.append({"group": parts[1], "item": f"Bank statements for {parts[1]}", "decision": "already_provided",
                      "reason": "This year's bank export has been received.", "sources": [parts[0]],
                      "documents": [p[0] for p in by("D") if parts[1].split()[0] in p[1]][:1]})
    for parts in by("T")[:4]:
        items.append({"group": "Last year's accounts", "item": f"Evidence for {parts[1]} this year", "decision": "request",
                      "reason": f"{parts[1]} was in last year's accounts and will be needed again.", "sources": [parts[0]], "documents": []})
    lessons = [parts[0] for parts in by("L")]
    text = json.dumps({
        "business_nature": {"type": btype, "summary": f"Demo: treated as {btype.replace('_', ' ')}.", "reasoning": "Keywords in the questionnaire.",
                            "sources": q_ids, "facts": [{"text": "Demo fact from the questionnaire.", "sources": q_ids[:1]}]},
        "items": items, "preparer_notes": [], "lessons_applied": lessons,
    })
    return AIMessage(content=text, usage_metadata=_usage(body, text))


def demo_review(body: str, by) -> AIMessage:
    """Stand-in for the review (demo mode and tests): a failed code check becomes a finding, each
    open earlier finding stays open, and each assumption needs evidence unless an E line backs it."""
    findings = [{"ref": "", "area": "Comparatives", "fs_line": parts[1][:60], "issue": f"Demo: {parts[1]} failed.",
                 "why": "A code check failed.", "severity": "high", "action": "Correct the draft.", "sources": [parts[0]], "assumptions": []}
                for parts in by("C") if len(parts) > 2 and parts[2] == "FAILED"][:3]
    open_refs = re.findall(r"^(R\d+) \| open \|", body, re.M)
    findings += [{"ref": ref, "area": "Earlier finding", "fs_line": "", "issue": "Demo: still open.", "why": "Not yet shown fixed.",
                  "severity": "medium", "action": "Fix it.", "sources": [p[0] for p in by("S")][:1], "assumptions": []} for ref in open_refs]
    assumptions = re.findall(r"^(A\d+) \| ", body, re.M)
    evidence = [p[0] for p in by("E")]
    reviews = [{"assumption": a, "verdict": "supported" if evidence else "needs_evidence", "reason": "Demo verdict.", "sources": evidence[:1]}
               for a in assumptions]
    text = json.dumps({"summary": "Demo review.", "findings": findings, "resolved": [], "assumption_reviews": reviews,
                       "lessons_applied": [p[0] for p in by("L")]})
    return AIMessage(content=text, usage_metadata=_usage(body, text))


def demo_assistant(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    """Stand-in for the assistant (demo mode and tests): quotes the first passage found, or says
    nothing was found; drafts a lesson as a rule from the note itself."""
    body = _flatten(messages[-1].content)
    if body.startswith("Kind: "):
        note = re.search(r"^Accountant's note: (.*)$", body, re.M)
        text = json.dumps({"title": "Demo rule", "when": "Demo: in the same situation.", "do": (note.group(1) if note else "Follow the note."),
                           "why": "An AFIT accountant said so."})
        return AIMessage(content=text, usage_metadata=_usage(body, text))
    first = re.search(r"^(K\d+) \| \[[^\]]*\] (.*)$", body, re.M)
    answer = ({"answer": f"Demo: the documents say: {first.group(2)[:200]}", "status": "answered", "outside_job": False,
               "points": [{"text": f"The documents say: {first.group(2)[:200]}", "basis": "task_documents", "sources": [first.group(1)], "reference": ""}]}
              if first else
              {"answer": "Demo: nothing in this task's documents answers that.", "status": "not_found", "outside_job": False, "points": []})
    text = json.dumps(answer)
    return AIMessage(content=text, usage_metadata=_usage(body, text))


_fake: dict[str, ScriptedChatModel] = {}


def set_fake(role: str, responder: Responder) -> ScriptedChatModel:
    """Tests: script what a model says."""
    _fake[role] = ScriptedChatModel(responder=responder, name_=f"fake-{role}", calls=[])
    return _fake[role]


def reset_fakes() -> None:
    _fake.clear()


def _fake_model(role: str) -> ScriptedChatModel:
    if role not in _fake:
        set_fake(role, {"drafter": demo_drafter, "vision": demo_vision, "precheck": demo_precheck, "assistant": demo_assistant}[role])
    return _fake[role]


# --- real models ---------------------------------------------------------------------------

def model_id(role: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return f"fake-{role}"
    return {"vision": s.vision_model or s.reader_model, "drafter": s.judge_model, "assistant": s.judge_model, "precheck": s.precheck_model}[role]


def get_model(role: str, settings: Settings | None = None) -> BaseChatModel:
    """role: "precheck" (Opus: the professional pre-check) | "drafter" (Sonnet: drafting a
    Direction Note) | "vision" (Haiku: writing out an image). max_tokens is set on every call."""
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return _fake_model(role)
    from langchain_anthropic import ChatAnthropic

    common: dict[str, Any] = {"max_retries": 2, "timeout": 120}
    if s.anthropic_api_key:
        common["api_key"] = s.anthropic_api_key
    if role == "vision":
        return ChatAnthropic(model=s.vision_model or s.reader_model, max_tokens=s.image_max_tokens, **common)
    if role == "assistant":  # answers a question on the task card: Sonnet, short, no extended thinking
        return ChatAnthropic(model=s.judge_model, max_tokens=s.assistant_max_tokens, **common)
    if role == "drafter":
        extra: dict[str, Any] = {}
        if s.judge_thinking:
            extra["thinking"] = {"type": s.judge_thinking}
        if s.judge_effort:
            extra["effort"] = s.judge_effort
        return ChatAnthropic(model=s.judge_model, max_tokens=s.judge_max_tokens, **extra, **common)
    # The pre-check (Opus): thinking cannot be disabled; effort is the control. A long answer
    # takes minutes, so it gets a longer timeout.
    return ChatAnthropic(model=s.precheck_model, max_tokens=s.precheck_max_tokens, effort=s.precheck_effort,
                         **{**common, "timeout": s.precheck_timeout})


def prefix_is_cacheable(role: str, prefix_text: str, settings: Settings | None = None) -> bool:
    """A prefix shorter than the model's cache minimum is cheaper sent uncached; we never pad."""
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return False
    return est_tokens(prefix_text) >= s.cache_min_tokens[family(model_id(role, s))]


def text_of(message: AIMessage) -> str:
    return message.content if isinstance(message.content, str) else "".join(
        b.get("text", "") for b in message.content if isinstance(b, dict) and b.get("type") == "text"
    )


def stop_reason(message: AIMessage) -> str:
    return (getattr(message, "response_metadata", None) or {}).get("stop_reason", "") or ""
