"""Model access. Claude only, model ids from config (token rule 9: Haiku reads, Sonnet judges,
Opus only on escalation).

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


def demo_reader(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    """Keyword-overlap stand-in for a reader: cites the block that best matches the question,
    or says it is unclear. Deliberately simple — it exists to exercise the pipeline."""
    human = messages[-1]
    docs = [b for b in human.content if isinstance(b, dict) and b.get("type") == "document"]
    question = " ".join(b["text"] for b in human.content if isinstance(b, dict) and b.get("type") == "text")
    item = re.search(r"Direction Note item [^:]+: (.*)", question)
    asked = item.group(1) if item else question.split("Question:", 1)[-1].split("Answer in the finding format")[0]
    stop = {"this", "that", "with", "from", "have", "been", "were", "does", "agree", "check", "confirm", "review", "anywhere", "explained"}
    words = {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", asked.lower())} - stop
    best = (0, None, None, "")
    for d_index, doc in enumerate(docs):
        for b_index, block in enumerate(doc["source"]["content"]):
            score = len(words & {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", block["text"].lower())})
            if score > best[0]:
                best = (score, d_index, b_index, block["text"])
    prompt_text = "\n".join(_flatten(m.content) for m in messages)
    score, d_index, b_index, text = best
    if not score:
        line = "unclear|medium|No evidence found for this item|Where is this covered in the job folder?"
        return AIMessage(content=[{"type": "text", "text": line}], usage_metadata=_usage(prompt_text, line))
    open_point = re.search(r"\btbc\b|to follow|awaiting|query|\?\s*$|not yet|outstanding", text.lower())
    title = asked.strip().split("\n")[0][:70].rstrip(" ?.")
    if open_point:
        line = f"exception|medium|Open point: {title}|The document still shows this as open: {text[:80]}"
    else:
        line = f"addressed|low|{title}|The job folder shows this: {text[:90]}"
    cite = {"type": "content_block_location", "cited_text": text, "document_index": d_index,
            "document_title": docs[d_index].get("title", ""), "start_block_index": b_index, "end_block_index": b_index + 1}
    return AIMessage(content=[{"type": "text", "text": line, "citations": [cite]}], usage_metadata=_usage(prompt_text, line))


def demo_judge(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    payload = json.loads(_flatten(messages[-1].content).split("INPUT:", 1)[1])
    findings = []
    for f in payload["findings"]:
        findings.append({
            "id": f["id"], "direction_ref": f["direction_ref"], "area": f["area"], "status": f["status"],
            "severity": f["severity"], "kind": "rule" if f["source"] == "rule" else "fact",
            "title": f["title"], "why": f["why"], "evidence_ids": f["evidence_ids"], "source": f["source"],
            "confidence": "high" if f["source"] == "rule" else "medium",
        })
    open_items = sum(1 for f in findings if f["status"] != "addressed")
    text = json.dumps({"summary": f"{len(findings)} points checked; {open_items} need attention before review.", "findings": findings})
    prompt_text = "\n".join(_flatten(m.content) for m in messages)
    return AIMessage(content=text, usage_metadata=_usage(prompt_text, text))


def demo_escalate(messages: list[BaseMessage], kwargs: dict) -> AIMessage:
    payload = json.loads(_flatten(messages[-1].content).split("INPUT:", 1)[1])
    f = payload["finding"]
    text = json.dumps({"status": f["status"], "severity": f["severity"], "confidence": "medium", "why": f["why"]})
    return AIMessage(content=text, usage_metadata=_usage(_flatten(messages[-1].content), text))


_fake: dict[str, ScriptedChatModel] = {}


def set_fake(role: str, responder: Responder) -> ScriptedChatModel:
    """Tests: script what the reader, judge or escalation model says."""
    _fake[role] = ScriptedChatModel(responder=responder, name_=f"fake-{role}", calls=[])
    return _fake[role]


def reset_fakes() -> None:
    _fake.clear()


def _fake_model(role: str) -> ScriptedChatModel:
    if role not in _fake:
        set_fake(role, {"reader": demo_reader, "judge": demo_judge, "escalate": demo_escalate}[role])
    return _fake[role]


# --- real models ---------------------------------------------------------------------------

def model_id(role: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return f"fake-{role}"
    return {"reader": s.reader_model, "judge": s.judge_model, "escalate": s.escalate_model}[role]


def get_model(role: str, settings: Settings | None = None) -> BaseChatModel:
    """role: "reader" | "judge" | "escalate". max_tokens is set on every call (token rule 8)."""
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return _fake_model(role)
    from langchain_anthropic import ChatAnthropic

    common: dict[str, Any] = {"max_retries": 2, "timeout": 120}
    if s.anthropic_api_key:
        common["api_key"] = s.anthropic_api_key
    if s.refusal_fallbacks and role != "reader":
        common["betas"] = ["server-side-fallback-2026-07-01"]
        common["model_kwargs"] = {"fallbacks": "default"}
    if role == "reader":
        # Haiku 4.5: no thinking unless asked for, and it rejects the effort parameter.
        return ChatAnthropic(model=s.reader_model, max_tokens=s.reader_max_tokens, **common)
    if role == "judge":
        extra: dict[str, Any] = {}
        if s.judge_thinking:
            extra["thinking"] = {"type": s.judge_thinking}
        if s.judge_effort:
            extra["effort"] = s.judge_effort
        return ChatAnthropic(model=s.judge_model, max_tokens=s.judge_max_tokens, **extra, **common)
    # Escalation (Opus 5.5): thinking cannot be disabled; effort is the only control.
    return ChatAnthropic(model=s.escalate_model, max_tokens=s.escalate_max_tokens, effort=s.escalate_effort, **common)


def prefix_is_cacheable(role: str, prefix_text: str, settings: Settings | None = None) -> bool:
    """Token rule 5: a prefix shorter than the model's cache minimum (4,096 tokens on Haiku 4.5)
    is cheaper sent uncached, and we never pad a prompt to reach the minimum."""
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
