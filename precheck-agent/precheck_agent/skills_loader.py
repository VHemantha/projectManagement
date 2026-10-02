"""Agent Skills kept in this repository (skills/<name>/SKILL.md) and loaded on demand.

Only each skill's name and description sit in a prompt; the body is added when a reader loads
it. They are deliberately NOT uploaded to the hosted Skills API: client data stays in this
service, and hosted Skills run in a sandbox with no network access and are not covered by
zero-data-retention terms.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from langchain.tools import tool

from .config import get_settings
from .textutil import sha


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    version: str  # declared version + a hash of the body, so any edit changes cache keys


def _parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} has no front matter")
    _, front, body = text.split("---", 2)
    meta: dict[str, str] = {}
    for line in front.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    body = body.strip()
    return Skill(
        name=meta["name"],
        description=meta["description"],
        body=body,
        version=f"{meta.get('version', '0')}+{sha(body)[:8]}",
    )


@lru_cache
def all_skills() -> dict[str, Skill]:
    root = Path(get_settings().skills_dir)
    skills = [_parse(p) for p in sorted(root.glob("*/SKILL.md"))]
    return {s.name: s for s in skills}


def get_skill(name: str) -> Skill:
    return all_skills()[name]


def skill_index(exclude: tuple[str, ...] = ()) -> str:
    """One line per skill (name and description only) for a system prompt."""
    return "\n".join(f"- {s.name}: {s.description}" for s in all_skills().values() if s.name not in exclude)


@tool
def load_skill(skill_name: str) -> str:
    """Load the full instructions of one skill by name. Use it only when the skill's
    description says it covers what you need and its instructions are not already in front
    of you."""
    skill = all_skills().get(skill_name.strip())
    if skill is None:
        return f"No skill named '{skill_name}'. Available: {', '.join(all_skills())}."
    return skill.body
