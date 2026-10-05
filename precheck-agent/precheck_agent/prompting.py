"""Small helpers shared by the model calls (pre-check, Direction Note drafting)."""
from langchain_core.messages import SystemMessage

from .config import Settings
from .llm import prefix_is_cacheable


def system_message(role: str, text: str, settings: Settings) -> SystemMessage:
    """A system prompt, marked for the 5-minute prompt cache when it is long enough to be cached
    by that role's model (below the minimum a marker does nothing, and we never pad)."""
    if prefix_is_cacheable(role, text, settings):
        return SystemMessage(content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}])
    return SystemMessage(content=text)
