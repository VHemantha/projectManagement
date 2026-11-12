"""The CEO asks the agent to talk with someone (AFIT, 12 Nov 2026): "chat with Pat and find out why
SMITH-1 is late", "guide Lee on the client's GST question and tell me what's going on".

1. In the CEO's conversation, the model decides who to contact, about which job, and what to ask
   ("contact" in its answer). Code checks the person and the job, sends the questions to that person
   in their private conversation with the agent, and tells the CEO exactly what was sent. The agent
   never says it has messaged someone unless code has sent it.
2. When the person replies, the agent sees what the CEO wants, what the CEO asked it to pass on, and
   what it knows (the job's records and the firm's knowledge base): it guides them, asks again if a
   question is still unanswered, and writes what they said and its recommendation for the CEO.
3. Code posts that report in the CEO's conversation. No reply within the reply window: one
   reminder, then the CEO is told.

What the person writes is information, never an instruction to the agent.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from . import policies, services
from .models import AgentAction, Inquiry

logger = logging.getLogger(__name__)
MAX_ROUNDS = 3  # replies read before reporting whatever was found
MAX_QUESTIONS = 4
MAX_PEOPLE = 80
OPEN_STATES = (Inquiry.State.ASKING, Inquiry.State.NO_REPLY)  # a late reply is still reported

CONTACT_SCHEMA = {
    "type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["person_id", "job_key", "purpose", "questions", "note_for_person", "ceo_guidance"],
        "properties": {
            "person_id": {"type": "integer"}, "job_key": {"type": "string"}, "purpose": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "string"}},
            "note_for_person": {"type": "string"}, "ceo_guidance": {"type": "string"},
        }}}

ANSWER_SCHEMA = {
    "type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["inquiry_id", "findings", "complete", "report_to_ceo"],
        "properties": {
            "inquiry_id": {"type": "integer"}, "findings": {"type": "string"}, "complete": {"type": "boolean"},
            "report_to_ceo": {"type": "string"},
        }}}

CEO_RULES = """
Talking with staff for the CEO:
- When the CEO asks you to chat with, ask, check with, follow up or guide someone (or to find out reasons from them), add one entry to "contact" for each person: their person_id from PEOPLE YOU CAN MESSAGE, the job key if it is about a job ("" if not), the purpose (what the CEO wants to know or achieve, one sentence), one to four clear, specific questions that will get the CEO the reasons or facts needed (use the job facts so the questions are concrete; never accusatory), note_for_person (anything the CEO wants passed on straight away, "" if none) and ceo_guidance (what the CEO wants them guided on, the CEO's view or instruction, "" if none).
- Code sends the questions and adds a confirmation with exactly what was asked, so in your reply just say briefly that you are asking them and will report back here. Never say you have messaged or will message anyone without adding them to "contact". If you cannot tell who the CEO means, ask the CEO and leave "contact" empty.
- When the CEO asks what someone said, answer from YOUR REQUESTS TO STAFF below."""

PERSON_RULES = """
The CEO has asked you to find something out from {first} (see THE CEO ASKED YOU TO FIND OUT below). In your reply:
- Thank them and respond to what they said. Then guide them: pass on what the CEO wants them guided on, and give one to three practical next steps from what the agent knows (the job's records and the firm's knowledge base below). Never invent a fact; for a technical tax question, point them to Ask on the task.
- If a question the CEO needed answered is still unanswered, ask it once more, plainly.
- In "inquiries", for each request below: findings (what they said that answers the CEO, facts only, close to their own words; "" if nothing yet), complete (true when the questions are answered or they clearly cannot say more), and report_to_ceo (when complete: a short report for the CEO, under 120 words: what you found, the reason given, what you advised them, and your recommendation for the CEO, if any. Keep facts apart from inference; "" if not complete)."""


def first_name(user) -> str:
    return (user.display_name or user.username).split(" ")[0]


def people_lines(ceo) -> list[str]:
    from apps.accounts.models import User

    staff = User.objects.filter(is_active=True, is_agent=False).exclude(pk=ceo.pk).order_by("display_name")[:MAX_PEOPLE]
    return [f"{u.pk}: {u.display_name or u.username}" + (f" — {u.job_title}" if u.job_title else "") for u in staff] or ["(nobody)"]


def requests_lines(ceo) -> list[str]:
    """The CEO's recent requests and what came of them."""
    lines = []
    for q in Inquiry.objects.filter(requested_by=ceo).select_related("person", "issue")[:10]:
        head = f"#{q.pk} {q.person.display_name}{' on ' + q.issue.key if q.issue_id else ''} ({q.opened_at:%d %b}): {q.purpose} — {q.get_state_display().lower()}"
        said = " | ".join(f["text"] for f in q.findings)[:600]
        lines.append(head + (f". They said: {said}" if said else "") + (f". Reported: {q.report[:400]}" if q.report else ""))
    return lines or ["(none)"]


def knowledge_for(issue) -> list[str]:
    """What the agent knows of a job for guiding someone: the job's records (the pre-check, review
    points, Direction Note, sub-tasks, earlier reasons) and the firm's knowledge base (answers the AI
    gave on this task, the accountant's answers, and the firm's active AI rules for this kind of job)."""
    from apps.precheck.models import PrecheckLesson

    from .advice import job_knowledge, latest_precheck

    lines = job_knowledge(issue)
    asked = list(issue.assistant_questions.filter(status="answered").order_by("-created_at")[:3])
    if asked:
        lines.append("Answers from the AI assistant on this task: " + " | ".join(
            f"Q: {q.question[:160]} A: {' '.join(q.answer.split())[:300]}" for q in asked))
    answers = list(issue.accountant_answers.order_by("-answered_at")[:3])
    if answers:
        lines.append("The accountant's answers on this task: " + " | ".join(f"{a.question[:120]} — {a.answer[:200]}" for a in answers))
    nature = ((latest_precheck(issue).get("business_nature") or {}).get("type") or "")
    rules = PrecheckLesson.objects.filter(status=PrecheckLesson.Status.ACTIVE)
    rules = rules.filter(issue=issue) | rules.filter(scope=PrecheckLesson.Scope.FIRM, precheck_type__in=[nature, ""] if nature else [""])
    rules = list(rules.order_by("-id")[:5])
    if rules:
        lines.append("The firm's AI rules that apply: " + " | ".join(
            (f"{r.rule_title}: {r.rule_do}" if r.rule_do else (f"{r.item}: " if r.item else "") + r.note)[:250] for r in rules))
    return lines


def open_for(person) -> list[Inquiry]:
    return list(Inquiry.objects.filter(person=person, state__in=OPEN_STATES).select_related("issue", "requested_by").order_by("opened_at")[:3])


def person_context(inquiries: list[Inquiry]) -> list[str]:
    lines = []
    for q in inquiries:
        ceo = q.requested_by.display_name if q.requested_by else "The CEO"
        lines += [f"\n== THE CEO ASKED YOU TO FIND OUT (request {q.pk}) ==",
                  f"{ceo} (the CEO) said: {q.request[:800]}", f"What the CEO wants: {q.purpose}",
                  "What you asked: " + " | ".join(q.questions)]
        if q.ceo_guidance:
            lines.append(f"What the CEO wants them guided on: {q.ceo_guidance}")
        if q.findings:
            lines.append("What they have said so far: " + " | ".join(f["text"] for f in q.findings))
        if q.issue_id:
            lines.append(f"What the agent knows about {q.issue.key} (job records and the firm's knowledge base):")
            lines += [f"  {line}" for line in knowledge_for(q.issue)]
    return lines


def opening_text(q: Inquiry) -> str:
    ceo = first_name(q.requested_by) if q.requested_by else "The CEO"
    about = f" about {q.issue.key} {q.issue.summary}" if q.issue_id else ""
    parts = [f"Hi {first_name(q.person)}. {ceo} has asked me to check in with you{about}."]
    if q.note_for_person:
        parts.append(f"{ceo} says: {q.note_for_person}")
    parts.append("\n".join(f"{n}. {text}" for n, text in enumerate(q.questions, 1)))
    parts.append("A short reply here is all I need, and I'll help with anything that's holding you up.")
    return "\n\n".join(parts)


def start(ceo, contacts: list[dict], jobs: list, message, *, cost_usd: float = 0.0) -> list[str]:
    """Send each person the CEO asked about their questions. Returns lines for the CEO's reply,
    saying exactly what was sent (or why not)."""
    from apps.accounts.models import User
    from apps.issues.models import Issue

    from .conversation import _text_of

    by_key = {i.key.upper(): i for i in jobs}
    request = _text_of(message.body)
    out = []
    for c in contacts or []:
        person = User.objects.filter(pk=c.get("person_id"), is_active=True, is_agent=False).first()
        if person is None or person.pk == ceo.pk:
            out.append("I couldn't tell who to message for that. Who should I ask?")
            continue
        key = str(c.get("job_key", "")).strip().upper()
        issue = by_key.get(key) or (Issue.objects.filter(key__iexact=key).first() if key else None)
        questions = [" ".join(str(t).split()) for t in c.get("questions") or [] if str(t).strip()][:MAX_QUESTIONS]
        purpose = " ".join(str(c.get("purpose", "")).split())[:500]
        if not questions:
            questions = [purpose or "Could you give me an update on how things are going, and whether anything is holding you up?"]
        q = Inquiry.objects.create(requested_by=ceo, person=person, issue=issue, request=request[:2000], purpose=purpose or questions[0][:500],
                                   questions=questions, note_for_person=str(c.get("note_for_person", ""))[:1000],
                                   ceo_guidance=str(c.get("ceo_guidance", ""))[:1500])
        # The CEO asked for this in person, so it goes to them even in shadow mode.
        sent = services.post_as_agent(services.conversation_for(person), opening_text(q))
        q.asked_message, q.last_asked_at = sent, timezone.now()
        q.save(update_fields=["asked_message", "last_asked_at"])
        AgentAction.objects.create(trigger="ceo_inquiry", target=person, issue=issue, reason=f"Asked {person.display_name} for the CEO: {q.purpose}"[:500],
                                   message=sent, cost_usd=cost_usd, detail={"inquiry": q.pk, "text": opening_text(q)})
        cost_usd = 0.0  # the model's cost is counted once
        about = f" about {issue.key}" if issue else ""
        out.append(f"I've messaged {person.display_name}{about} and asked:\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(questions, 1))
                   + "\nI'll report back here when they reply.")
    return out


def record(person, answers: list[dict], inquiries: list[Inquiry], reply_text: str, words: str) -> None:
    """The person replied: keep what they said and, when the questions are answered (or after a few
    replies), report to the CEO in the CEO's conversation."""
    by_id = {q.pk: q for q in inquiries}
    given = {a.get("inquiry_id"): a for a in answers or [] if a.get("inquiry_id") in by_id}
    now = timezone.now()
    for q in inquiries:
        a = given.get(q.pk)
        if a is None and answers is not None and len(inquiries) > 1:
            continue  # the model said this reply was about another request
        found = " ".join(str((a or {}).get("findings", "")).split()) or (words if a is None else "")
        if found:
            q.findings = q.findings + [{"at": now.isoformat(), "text": found[:1000]}]
        q.rounds += 1
        complete = bool((a or {}).get("complete")) or a is None or q.rounds >= MAX_ROUNDS
        if complete and q.findings:
            report = " ".join(str((a or {}).get("report_to_ceo", "")).split())
            _report(q, report, reply_text)
        q.save()


def _report(q: Inquiry, report: str, reply_text: str) -> None:
    about = f" on {q.issue.key}" if q.issue_id else ""
    said = "\n".join(f"– {f['text']}" for f in q.findings)
    text = f"{q.person.display_name} replied{about}. You asked: {q.purpose}\n\nWhat they said:\n{said}"
    if report:
        text += f"\n\n{report}"
    told = reply_text.split("\n\nNoted for ")[0].strip()
    if told:
        text += f"\n\nWhat I told {first_name(q.person)}: {told}"
    ceo = q.requested_by or services.ceo()
    if ceo is not None:
        sent = services.post_as_agent(services.conversation_for(ceo), text)
        AgentAction.objects.create(trigger="ceo_inquiry_report", target=ceo, issue=q.issue, reason=f"Reported {q.person.display_name}'s reply"[:500],
                                   message=sent, detail={"inquiry": q.pk, "text": text})
    q.state, q.report, q.reported_at = Inquiry.State.REPORTED, text[:5000], timezone.now()


def chase(now) -> dict:
    """No reply within the reply window: remind them once; after a second window, tell the CEO."""
    nudged = told = 0
    for q in Inquiry.objects.filter(state=Inquiry.State.ASKING, rounds=0, last_asked_at__isnull=False).select_related("person", "issue", "requested_by"):
        window = timedelta(hours=float(policies.resolve("reply_window_hours", job=q.issue, person=q.person)))
        if now < q.last_asked_at + window:
            continue
        if not q.nudged:
            text = (f"Hi {first_name(q.person)}, just following up on {first_name(q.requested_by) if q.requested_by else 'the CEO'}'s questions"
                    f"{' about ' + q.issue.key if q.issue_id else ''}:\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(q.questions, 1)))
            sent = services.post_as_agent(services.conversation_for(q.person), text)
            AgentAction.objects.create(trigger="ceo_inquiry", target=q.person, issue=q.issue, reason="Reminder for the CEO's questions",
                                       message=sent, detail={"inquiry": q.pk, "text": text})
            q.nudged, q.last_asked_at = True, now
            q.save(update_fields=["nudged", "last_asked_at"])
            nudged += 1
            continue
        ceo = q.requested_by or services.ceo()
        if ceo is not None:
            services.post_as_agent(services.conversation_for(ceo), f"{q.person.display_name} hasn't replied to your questions"
                                   f"{' about ' + q.issue.key if q.issue_id else ''} ({q.purpose}), after a reminder. "
                                   "I'll pass on their answer if they reply; you may want to speak with them directly.")
        q.state = Inquiry.State.NO_REPLY
        q.save(update_fields=["state"])
        told += 1
    return {"reminded": nudged, "no_reply": told}
