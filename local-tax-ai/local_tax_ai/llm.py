"""The model (LangChain's ChatAnthropic) and the demo stand-in (AFIT, 22 Nov 2026). Every call asks for a JSON
answer in the agent's schema; the answer is then checked with pydantic (graphs.py)."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from .config import Settings, get_settings


class Unusable(Exception):
    """The model's answer could not be used (refused, cut short, not the shape asked)."""


def model(settings: Settings | None = None, *, reader: bool = False):
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return None
    from langchain_anthropic import ChatAnthropic

    kwargs = {"max_retries": 2, "timeout": s.timeout_s}
    if s.api_key:
        kwargs["api_key"] = s.api_key
    return ChatAnthropic(model=s.reader_model if reader else s.model, max_tokens=s.reader_max_tokens if reader else s.max_tokens, **kwargs)


def ask(system: str, content, schema: dict, *, reader: bool = False, fake=None, settings: Settings | None = None) -> dict:
    """One call: the system prompt, the user content (text, or content blocks with a document), the JSON schema the
    answer must follow. In fake mode, `fake(content)` gives the answer."""
    s = settings or get_settings()
    if s.llm_mode == "fake":
        return json.loads(json.dumps(fake(content) if fake else {}))  # as the real answer arrives: plain JSON
    message = model(s, reader=reader).invoke([SystemMessage(content=system), HumanMessage(content=content)],
                                              output_config={"format": {"type": "json_schema", "schema": schema}})
    stop = (getattr(message, "response_metadata", None) or {}).get("stop_reason", "")
    if stop in ("refusal", "max_tokens"):
        raise Unusable(f"The model stopped early ({stop}).")
    text = message.content if isinstance(message.content, str) else "".join(
        b.get("text", "") for b in message.content if isinstance(b, dict) and b.get("type") == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Unusable("The model's answer was not valid JSON.") from exc
