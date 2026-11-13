"""Special notes from AFIT staff for one task (AFIT, 13 Nov 2026): "the client sold the rental in
June, treat it as a sale", "ignore the old ANZ account, it closed last year", "keep the email short,
the client is elderly". The PM application sends them with the job; each says which agents it is
for (the pre-check, the preparation guide, the review, Ask), or all of them.

Each agent is given its notes as SN lines and told to follow them, as the firm's instruction for
this task, and to cite the SN id wherever a note changed what it decided or wrote. Code then lists,
with every result, the notes the agent was given and which ones it cited, so people can see that
their note was considered.

A note is an instruction about the work, not about the agent's rules: it never overrides the
documents' facts, the law, or the rule that every figure must come from the input.
"""
import re

from .textutil import clip_words

AGENTS = ("precheck", "guide", "review", "ask")
MAX_NOTES = 20
PREFIX = "SN"
HEADING = ("SPECIAL NOTES FROM AFIT STAFF FOR THIS TASK (follow each one: it is the firm's instruction for this task and comes "
           "before your usual approach, but never before the facts in the documents or the law; if a note conflicts with them, "
           "follow the documents and say so. Cite the SN id in the sources of every item, finding, step, note or point a "
           "special note affected)")


def for_agent(job: dict, agent: str) -> list[dict]:
    """The task's notes meant for this agent: those naming it, and those for every agent."""
    notes = [n for n in job.get("special_notes") or [] if str(n.get("text", "")).strip()]
    return [n for n in notes if not n.get("agents") or agent in n["agents"]][:MAX_NOTES]


def section(job: dict, agent: str, index: dict) -> list[str]:
    """The SN lines for the model's input (and their ids in `index`); [] when there are none."""
    notes = for_agent(job, agent)
    if not notes:
        return []
    out = [f"\n== {HEADING} =="]
    for n, note in enumerate(notes, start=1):
        sid = f"{PREFIX}{n}"
        index[sid] = {"kind": "special_note", "note": note, "source_type": "special_note", "text": note["text"]}
        by = f"from {note['by']}" if note.get("by") else "from AFIT staff"
        out.append(f"{sid} | {by} | {' '.join(str(note['text']).split())[:1000]}")
    return out


def label(item: dict) -> str:
    return f"Special note: {clip_words(' '.join(str(item['note'].get('text', '')).split()), 14)}"


_ID = re.compile(rf"^{PREFIX}\d+$")


def cited_in(value) -> set[str]:
    """Every SN id found anywhere in a cleaned answer (in its sources)."""
    if isinstance(value, dict):
        return set().union(*(cited_in(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(cited_in(v) for v in value)) if value else set()
    return {value} if isinstance(value, str) and _ID.match(value) else set()


def considered(job: dict, agent: str, cleaned) -> list[dict]:
    """For the result: each note the agent was given, and whether it cited it."""
    cited = cited_in(cleaned)
    return [{"id": f"{PREFIX}{n}", "text": note["text"], "by": note.get("by", ""), "cited": f"{PREFIX}{n}" in cited}
            for n, note in enumerate(for_agent(job, agent), start=1)]
