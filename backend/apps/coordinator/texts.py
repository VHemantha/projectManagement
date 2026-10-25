"""What the coordination agent says when it raises something. Written by code from the job's facts,
so every figure and date is exact: direct and firm, never threatening, and it never assumes a delay
is anyone's fault (missing client documents are named as a likely cause, not held against anyone).
"""
from .models import AgentCase

K = AgentCase.Kind


def _hours(f) -> str:
    if f.budget_hours:
        return f"{f.actual_hours:.1f} of {f.budget_hours:.1f} budgeted hours used ({f.utilisation_pct}%)"
    return f"{f.actual_hours:.1f} hours logged (no budget set)"


def _client_note(f) -> str:
    if not f.outstanding:
        return ""
    return (f" The pre-check still lists {len(f.outstanding)} item{'s' if len(f.outstanding) != 1 else ''} to come from the client; "
            "if that is what's holding it up, say so and I'll note it.")


def _late(case, today) -> str:
    from .facts import working_days_late

    n = working_days_late(case.due_date, today, case.person) if case.due_date else 0
    return f"{n} working day{'s' if n != 1 else ''} overdue" if n else "overdue"


def ask_text(case: AgentCase, f, today, *, follow_up: bool = False) -> str:
    job = f"{f.key} {f.title} ({f.client})"
    due = f"{case.due_date:%a %d %b}" if case.due_date else ""
    again = "Following up: " if follow_up else ""
    if case.kind == K.URGENT_INACTIVE:
        return (f"{again}{job} is {f.priority} priority and its pre-check is due {due}, but I can't see any activity on it yet "
                "(no time logged, no pre-check). What's the status, and do you need anything to get started?")
    if case.kind == K.PRECHECK_DUE:
        return (f"{again}{job}: the pre-check is due {due} and hasn't been run yet. Are you on track? If not, tell me what's missing, "
                "when you expect to finish, and whether you need help.")
    if case.kind == K.PRECHECK_OVERDUE:
        return (f"{again}{job}: the pre-check was due {due} and is {_late(case, today)}. What's holding it up, and by when will it be "
                "done? I'll keep the original date on record alongside the new one.")
    if case.kind == K.PREP_DUE:
        return (f"{again}{job}: preparation is due {due}. {_hours(f)}. What's left to do, how many more hours do you need, and when will "
                f"you finish? Do you need help?{_client_note(f)}")
    if case.kind == K.PREP_OVERDUE:
        return (f"{again}{job}: preparation was due {due} and is {_late(case, today)}. {_hours(f)}. What is the cause, what's left, and "
                f"what is your revised completion date?{_client_note(f)}")
    if case.kind == K.PROMISE_MISSED:
        return (f"{again}{job}: you expected to finish by {due}, and it isn't marked done yet. What changed, and what is the new date? "
                "If it is done, stamp the stage on the task so the record shows it.")
    return f"{again}{job}: please give me an update."


def escalation_text(case: AgentCase, f) -> str:
    return (f"{case.person.display_name} hasn't given an update on {f.key} {f.title} ({f.client}) — {case.get_kind_display().lower()}, "
            f"due {case.due_date:%a %d %b} — after {case.asked} message{'s' if case.asked != 1 else ''}. {_hours(f)}.{_client_note(f)} "
            "Could you check in with them? I'll keep monitoring the job.")


def group_for_person(person, texts: list[str], *, escalation: bool = False) -> str:
    first = (person.display_name or person.username).split(" ")[0]
    if len(texts) == 1:
        return f"Hi {first}. {texts[0]}"
    head = f"Hi {first}, {'a few jobs need your attention' if escalation else 'a few things on your jobs'}:"
    return head + "\n\n" + "\n\n".join(f"• {t}" for t in texts) + "\n\nOne reply covering all of them is fine."


def shadow_digest(digest: list[tuple]) -> str:
    """Shadow mode: what the agent would have sent, for the CEO to review."""
    parts = [f"Shadow mode — I would have sent {len(digest)} message{'s' if len(digest) != 1 else ''} just now. Nothing went to the team."]
    for person, text in digest:
        parts.append(f"To {person.display_name}:\n{text}")
    parts.append("Turn shadow mode off in the coordinator console when you're happy with these.")
    return "\n\n".join(parts)
