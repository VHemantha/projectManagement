"""The Local Tax workflow API (AFIT, 22 Nov 2026), for Team 3 > Local's cards only - any other card is "not
found" here, so nothing about other cards changes.

GET    /api/local-tax/tasks/<key>/                          the engagement and everything worked out from it
PATCH  /api/local-tax/tasks/<key>/                          the questionnaire and the computation's lines
PUT    /api/local-tax/tasks/<key>/tb/                       the trial balance (rows), replacing it
POST   /api/local-tax/tasks/<key>/tb/upload/                the trial balance from an Excel or CSV file
PATCH  /api/local-tax/tasks/<key>/tb/<code>/                one account's FS heading
POST   /api/local-tax/tasks/<key>/adjustments/              propose a journal, tax adjustment or correction
PATCH  /api/local-tax/tasks/<key>/adjustments/<id>/         edit a proposal (the earlier version is kept)
POST   /api/local-tax/tasks/<key>/adjustments/<id>/decide/  approve or reject (a reviewer, lead or admin)
POST   /api/local-tax/tasks/<key>/reverse/effect/           a hypothetical change's effect (nothing stored)
POST   /api/local-tax/tasks/<key>/stages/<stage>/           a stage's status
GET    /api/local-tax/tasks/<key>/events/                   the audit trail
GET    /api/local-tax/tasks/<key>/export/<doc>.<fmt>        fs | computation | return, as pdf or xlsx
POST   /api/local-tax/tasks/<key>/ai/<agent>/               Local_Tax_AI: chat, map-tb, analyse, reverse, return, extract
POST   /api/local-tax/tasks/<key>/messages/<id>/changes/<n>/  a change the client asked for (from the chat): apply | dismiss
POST   /api/local-tax/tasks/<key>/fs/edit/                  a statement line's figure edited (DELETE: an edit, or all, undone)
POST   /api/local-tax/tasks/<key>/fs/edits/post/            balanced statement edits posted to the trial balance (a journal)
POST   /api/local-tax/tasks/<key>/update/                   Update: everything worked out again, and what changed since the last update
GET    /api/local-tax/rules/                                 the years with rules; /rules/<ya>/ one year's rules
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.keys import get_issue_or_404
from apps.issues.models import Attachment

from . import ai, services as S, validation as V
from .engine import fs as FS
from .engine import reverse as RV
from .engine.rules import MissingRules, load, years
from . import client_requests as CR
from .models import Adjustment, AiMessage, TaxEngagement, TbLine


def _engagement(request, key) -> TaxEngagement:
    issue = get_issue_or_404(key)
    if not S.is_local_tax(issue):
        raise Http404("The Local Tax workflow applies to Team 3 > Local's cards only.")
    if not S.can_open(request.user, issue):
        raise PermissionDenied("You can't open this task.")
    return S.engagement_for(issue, request.user)


def _state(request, eng):
    eng.refresh_from_db()
    return Response(S.state(eng, request.user))


class EngagementView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        return _state(request, _engagement(request, key))

    @transaction.atomic
    def patch(self, request, key):
        eng = _engagement(request, key)
        try:
            _edit(eng, request.user, request.data if isinstance(request.data, dict) else {})
        except V.Invalid as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        return _state(request, eng)


def _edit(eng, user, payload: dict) -> dict:
    """The questionnaire / client information edited (the PATCH, and a client's change applied from the chat): the
    changes made, logged with their reason. Raises V.Invalid."""
    fields, data = V.update(payload)
    changes = {}
    for f, v in fields.items():
        old = getattr(eng, f)
        if old != v:
            changes[f] = {"from": S._jsonable(old), "to": S._jsonable(v)}
            setattr(eng, f, v)
    new_data = dict(eng.data or {})
    for section, v in data.items():
        if section == "computation":
            v = {**(new_data.get("computation") or {}), **v}
        if section == "ppe":  # only the parts sent change; the approval record stays as it is
            v = {**(new_data.get("ppe") or {}), **v}
        if new_data.get(section) != v:
            changes[f"data.{section}"] = {"from": new_data.get(section), "to": v}
            new_data[section] = v
    if not changes:
        return changes
    # A value pre-filled from a document and then changed by hand keeps its trail.
    sources = dict(new_data.get("field_sources") or {})
    for f in fields:
        if f in changes and f in sources and "changed by" not in sources[f]:
            sources[f] = f"{sources[f]} - changed by {user.display_name}"
            new_data["field_sources"] = sources
    eng.data = new_data
    stage = payload.get("stage") if payload.get("stage") in TaxEngagement.STAGES else (
        "computation" if set(data) & {"computation"} else "return" if set(data) & {"return_overrides"} else "questionnaire")
    S.touch(eng, stage, user)
    eng.save()
    S.log(eng, user, "edited", {"stage": stage, "changes": changes, "reason": str(payload.get("reason") or "")[:500]})
    return changes


def _tb_rows(rows) -> list[dict]:
    out, seen = [], set()
    for n, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        code = " ".join(str(r.get("code") or "").split())[:40] or f"L{n + 1}"
        name = " ".join(str(r.get("name") or "").split())[:200]
        if not name or code in seen:
            continue
        seen.add(code)

        def num(v):
            if v in (None, ""):
                return None
            try:
                return Decimal(str(v).replace(",", "").replace("(", "-").replace(")", "")).quantize(Decimal("0.01"))
            except InvalidOperation:
                raise V.Invalid({f"tb.{n}": f"{name}: the amounts must be numbers."}) from None

        amount = num(r.get("amount"))
        if amount is None:
            amount = (num(r.get("debit")) or Decimal("0")) - (num(r.get("credit")) or Decimal("0"))
        out.append({"code": code, "name": name, "amount": amount, "comparative": num(r.get("comparative")),
                    "heading": r.get("heading") if r.get("heading") in FS.HEADINGS else ""})
    return out


def _replace_tb(eng, rows, user, source: str, kind: str = "upload", story: str = ""):
    """The trial balance replaced. `kind`: where it came from - "upload" (a file or a confirmed AI reading), "entered",
    or "story" (dummy data the AI made from a story: the statements say so wherever they are shown)."""
    old = {ln.code: ln for ln in eng.tb_lines.all()}
    eng.tb_lines.all().delete()
    for r in rows:
        prior = old.get(r["code"])
        heading, by = r["heading"], "person" if r["heading"] else "rule"
        if not heading and prior and prior.heading_by == "person":
            heading, by = prior.heading, "person"  # a person's mapping is kept across re-uploads
        if not heading:
            heading = FS.suggest_heading(r["name"], r["amount"])
        TbLine.objects.create(engagement=eng, code=r["code"], name=r["name"], amount=r["amount"], comparative=r["comparative"], heading=heading,
                              heading_by=by)
    S.touch(eng, "fs", user)
    eng.data = {**(eng.data or {}), "tb_source": {"kind": kind, "label": source[:200], "story": story[:4000], "at": timezone.now().isoformat(),
                                                  "by": user.display_name if getattr(user, "is_authenticated", False) else ""}}
    eng.save()
    S.log(eng, user, "trial_balance", {"source": source, "kind": kind, "accounts": len(rows), "total": str(sum((r["amount"] for r in rows), Decimal("0")))})


class TrialBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, key):
        eng = _engagement(request, key)
        try:
            rows = _tb_rows(request.data.get("rows") or [])
        except V.Invalid as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        story = " ".join(str(request.data.get("story") or "").split())
        if request.data.get("source") == "story":
            if len(story) < 20:
                return Response({"story": ["Give the story the dummy trial balance was made from."]}, status=status.HTTP_400_BAD_REQUEST)
            _replace_tb(eng, rows, request.user, "Dummy trial balance made by Local_Tax_AI from a story", kind="story", story=story)
        elif request.data.get("source") == "instructions":
            # drafted by Local_Tax_AI from the accountant's own figures (AFIT, 26 Nov 2026), reviewed before it was added: not dummy data
            _replace_tb(eng, rows, request.user, "Drafted by Local_Tax_AI from the accountant's instructions", kind="instructions", story=story)
        else:
            _replace_tb(eng, rows, request.user, "entered", kind="entered")
        return _state(request, eng)


class TrialBalanceUploadView(APIView):
    """An Excel (.xlsx) or CSV trial balance: columns code, name (or account), debit, credit (or amount), and
    optionally comparative. Read by code; the AI is not involved in the figures."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, key):
        from .tbimport import TbImportError, read

        eng = _engagement(request, key)
        f = request.FILES.get("file")
        if f is None:
            return Response({"file": ["Choose the trial balance file."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows = _tb_rows(read(f.read(), f.name))
        except (TbImportError, V.Invalid) as exc:
            return Response({"file": [str(getattr(exc, "errors", exc))]}, status=status.HTTP_400_BAD_REQUEST)
        if not rows:
            return Response({"file": ["No accounts were found in the file."]}, status=status.HTTP_400_BAD_REQUEST)
        _replace_tb(eng, rows, request.user, f.name)
        return _state(request, eng)


class TbLineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def patch(self, request, key, code):
        eng = _engagement(request, key)
        line = get_object_or_404(TbLine, engagement=eng, code=code)
        heading = request.data.get("heading")
        if heading not in FS.HEADINGS:
            return Response({"heading": ["Choose a heading."]}, status=status.HTTP_400_BAD_REQUEST)
        old = line.heading
        line.heading, line.heading_by, line.heading_note = heading, "person", str(request.data.get("note") or "")[:300]
        line.save()
        S.touch(eng, "fs", request.user)
        eng.save()
        S.log(eng, request.user, "mapping", {"code": code, "from": old, "to": heading})
        return _state(request, eng)


def _adjustment_fields(eng, data, levers) -> tuple[dict, dict]:
    errors, out = {}, {}
    kind = data.get("kind")
    if kind not in Adjustment.Kind.values:
        errors["kind"] = "Choose journal, reclassification, tax adjustment or correction."
    reason = " ".join(str(data.get("reason") or "").split())
    if len(reason) < 5:
        errors["reason"] = "Say why, in a few words."
    out.update(kind=kind, reason=reason[:2000], label=" ".join(str(data.get("label") or "").split())[:200],
               evidence_note=str(data.get("evidence_note") or "")[:500])
    if data.get("entry_date"):
        try:
            from datetime import date as _d

            out["entry_date"] = _d.fromisoformat(str(data["entry_date"])[:10])
        except ValueError:
            errors["entry_date"] = "Give the journal's date (YYYY-MM-DD)."
    if data.get("evidence_id"):
        att = Attachment.objects.filter(pk=data["evidence_id"], issue=eng.issue).first()
        if att is None:
            errors["evidence_id"] = "Choose a document attached to this task."
        out["evidence"] = att
    lines = data.get("lines") or []
    if kind in ("journal", "reclass") or (kind == "reverse" and lines):
        clean, total = [], Decimal("0")
        for n, ln in enumerate(lines if isinstance(lines, list) else []):
            try:
                amount = Decimal(str(ln.get("amount")).replace(",", "")).quantize(Decimal("0.01"))
            except (InvalidOperation, AttributeError):
                errors[f"lines.{n}"] = "Give each line's amount."
                continue
            code = str(ln.get("code") or "").strip()[:40]
            if not code:
                errors[f"lines.{n}"] = "Give each line's account."
            clean.append({"code": code, "name": str(ln.get("name") or "")[:200], "amount": str(amount), "heading": ln.get("heading") or ""})
            total += amount
        if len(clean) < 2:
            errors["lines"] = "A journal needs at least two lines (debit and credit)."
        elif total != 0:
            errors["lines"] = f"The journal doesn't balance: debits and credits differ by {total:,.2f}."
        out.update(lines=clean, scope="accounting", target=clean[0]["code"] if clean else "")
        if kind == "reverse":
            lever = next((lv for lv in levers if lv["key"] == data.get("target")), None)
            out.update(original=lever["amount"] if lever else None, proposed=Decimal(str(data.get("proposed"))) if data.get("proposed") not in (None, "") else None)
    else:
        lever = next((lv for lv in levers if lv["key"] == data.get("target")), None)
        if lever is None:
            errors["target"] = "Choose the computation line to change."
        elif lever["scope"] != "tax":
            errors["target"] = "That is an accounting line: correct it with a journal (debit and credit), so the statements stay balanced."
        try:
            proposed = Decimal(str(data.get("proposed")).replace(",", "")).quantize(Decimal("0.01"))
        except (InvalidOperation, AttributeError):
            errors["proposed"] = "Give the corrected amount."
            proposed = None
        out.update(scope="tax", target=data.get("target") or "", original=lever["amount"] if lever else None, proposed=proposed,
                   label=out["label"] or (lever["label"] if lever else ""))
    if not out["label"]:
        out["label"] = (lines[0].get("name") if lines and isinstance(lines[0], dict) else "") or "Adjustment"
    return out, errors


class AdjustmentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        eng = _engagement(request, key)
        state = S.state(eng, request.user)
        fields, errors = _adjustment_fields(eng, request.data, state.get("levers") or [])
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        _propose(eng, request.user, fields)
        return _state(request, eng)


def _propose(eng, user, fields: dict) -> Adjustment:
    """A checked journal or adjustment proposed (a journal gets the register's next reference)."""
    if fields["kind"] in ("journal", "reclass"):
        fields["ref"] = S.next_ref(eng)
        fields.setdefault("entry_date", eng.fy_end)
    adj = Adjustment.objects.create(engagement=eng, created_by=user, **fields)
    S.log(eng, user, "adjustment_proposed", {"id": adj.id, **S.adjustment_dict(adj)})
    return adj


class AdjustmentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def patch(self, request, key, pk):
        eng = _engagement(request, key)
        adj = get_object_or_404(Adjustment, engagement=eng, pk=pk)
        if adj.target.startswith("auto:"):
            return Response({"detail": "The depreciation journal follows the depreciation schedule: change the schedule and approve it again."},
                            status=status.HTTP_409_CONFLICT)
        if adj.status != Adjustment.Status.PROPOSED:
            return Response({"detail": "Only a proposed adjustment can be edited; propose a new one."}, status=status.HTTP_409_CONFLICT)
        state = S.state(eng, request.user)
        fields, errors = _adjustment_fields(eng, {**S.adjustment_dict(adj), "evidence_id": adj.evidence_id, **request.data}, state.get("levers") or [])
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        adj.history = [*adj.history, {**{k: v for k, v in S.adjustment_dict(adj).items() if k in ("label", "original", "proposed", "lines", "reason", "entry_date")},
                                       "at": timezone.now().isoformat(), "by": request.user.display_name}]
        for k, v in fields.items():
            setattr(adj, k, v)
        adj.save()
        S.log(eng, request.user, "adjustment_edited", {"id": adj.id})
        return _state(request, eng)


class AdjustmentDecideView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, pk):
        eng = _engagement(request, key)
        if not S.can_approve(request.user, eng.issue):
            raise PermissionDenied("Only a reviewer, a lead or an admin can approve or reject an adjustment.")
        adj = get_object_or_404(Adjustment, engagement=eng, pk=pk)
        decision = request.data.get("decision")
        if decision not in ("approve", "reject"):
            return Response({"decision": ["approve or reject"]}, status=status.HTTP_400_BAD_REQUEST)
        if adj.status != Adjustment.Status.PROPOSED:
            return Response({"detail": f"Already {adj.status}."}, status=status.HTTP_409_CONFLICT)
        if decision == "approve" and adj.kind == "reverse" and not (adj.evidence_id or adj.evidence_note.strip()):
            return Response({"detail": "A correction from the reverse tax analysis needs its supporting evidence before it can be approved."},
                            status=status.HTTP_400_BAD_REQUEST)
        adj.status = Adjustment.Status.APPROVED if decision == "approve" else Adjustment.Status.REJECTED
        adj.decided_by, adj.decided_at, adj.decision_note = request.user, timezone.now(), str(request.data.get("note") or "")[:500]
        adj.save()
        if adj.target == "auto:fs_edits":
            from . import fs_edits as FE

            edits = FE.stored(eng)
            if adj.status == Adjustment.Status.APPROVED:
                eng.data = {**(eng.data or {}), "fs_edits": {"items": {}, "journal": None, "posted": adj.ref}}
            elif edits.get("journal") == adj.id:
                eng.data = {**(eng.data or {}), "fs_edits": {**edits, "journal": None}}
            eng.save()
        if adj.status == Adjustment.Status.APPROVED:
            S.touch(eng, "fs" if adj.scope == "accounting" else "computation", request.user)
            eng.save()
        S.log(eng, request.user, f"adjustment_{adj.status}", {"id": adj.id, "label": adj.label, "original": adj.original, "proposed": adj.proposed,
                                                             "note": adj.decision_note})
        return _state(request, eng)


class AdjustmentReverseView(APIView):
    """POST {reason} - an approved journal reversed: a reversing journal (each line's sign turned) is proposed, to be
    approved like any other. An approved journal is never edited or deleted, so the register keeps the whole trail."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, pk):
        eng = _engagement(request, key)
        adj = get_object_or_404(Adjustment, engagement=eng, pk=pk)
        if adj.target.startswith("auto:"):
            return Response({"detail": "The depreciation journal follows the depreciation schedule: change the schedule and approve it again."},
                            status=status.HTTP_409_CONFLICT)
        if adj.scope != "accounting" or adj.status != Adjustment.Status.APPROVED or not adj.lines:
            return Response({"detail": "Only an approved journal can be reversed."}, status=status.HTTP_409_CONFLICT)
        if adj.reversals.exclude(status=Adjustment.Status.REJECTED).exists():
            return Response({"detail": "This journal already has a reversal."}, status=status.HTTP_409_CONFLICT)
        reason = " ".join(str(request.data.get("reason") or "").split())
        if len(reason) < 5:
            return Response({"reason": ["Say why it is reversed."]}, status=status.HTTP_400_BAD_REQUEST)
        lines = [{**ln, "amount": str(-Decimal(str(ln["amount"])))} for ln in adj.lines]
        rev = Adjustment.objects.create(engagement=eng, kind=adj.kind, scope="accounting", target=adj.target, ref=f"{adj.ref or 'JE'}-R",
                                        label=f"Reversal of {adj.ref} {adj.label}".strip()[:200], lines=lines, reason=reason[:2000], reverses=adj,
                                        entry_date=adj.entry_date or eng.fy_end, created_by=request.user)
        S.log(eng, request.user, "adjustment_reversal_proposed", {"id": rev.id, "reverses": adj.id, "ref": rev.ref, "reason": reason})
        return _state(request, eng)


class ReverseEffectView(APIView):
    """What one change would do - hypothetical, stored nowhere."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key):
        eng = _engagement(request, key)
        fs_result = S.financials(eng)
        ins = S.inputs(eng, fs_result)
        try:
            out = RV.effect(ins, S.rules_for(eng.year_of_assessment), str(request.data.get("lever") or ""), request.data.get("proposed"), eng.expected_tax,
                            eng.expected_basis, S.pl_accounts(fs_result))
        except KeyError:
            return Response({"lever": ["Choose a line from this engagement."]}, status=status.HTTP_400_BAD_REQUEST)
        except (InvalidOperation, TypeError):
            return Response({"proposed": ["Give the amount."]}, status=status.HTTP_400_BAD_REQUEST)
        except MissingRules as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class StageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, stage):
        eng = _engagement(request, key)
        if stage not in TaxEngagement.STAGES:
            raise Http404
        wanted = request.data.get("status")
        if wanted not in TaxEngagement.STATUSES:
            return Response({"status": ["not_started, in_progress, ready_for_review or approved"]}, status=status.HTTP_400_BAD_REQUEST)
        if wanted in ("ready_for_review", "approved") and stage != "questionnaire":
            from . import fs_edits as FE

            edits = FE.summary(eng, S.fs_scope(eng) == "full")
            if edits and not edits["balanced"]:
                return Response({"detail": f"The statement edits are out of balance by {Decimal(edits['difference']):,.2f}: edit the other side "
                                           "before you continue."}, status=status.HTTP_409_CONFLICT)
        if wanted == "approved":
            if not S.can_approve(request.user, eng.issue):
                raise PermissionDenied("Only a reviewer, a lead or an admin can approve a stage.")
            order = list(TaxEngagement.STAGES)
            earlier = [s for s in order[: order.index(stage)] if eng.stage(s)["status"] != "approved"]
            if earlier:
                return Response({"detail": "Approve the earlier stages first: " + ", ".join(earlier) + "."}, status=status.HTTP_409_CONFLICT)
            st = S.state(eng, request.user)
            blocking = [a for a in st["alerts"] if a["stage"] == stage and a["severity"] == "blocking"]
            if blocking:
                return Response({"detail": "Resolve first: " + " ".join(a["text"] for a in blocking)}, status=status.HTTP_409_CONFLICT)
            # Phase 4: approving figures that rest on rules no tax professional has validated is a conscious decision.
            unvalidated = [r["rule"] for r in (st.get("computation") or {}).get("rules") or [] if not r["validated"]]
            if stage in ("computation", "return") and unvalidated:
                if not request.data.get("acknowledge_unvalidated"):
                    return Response({"detail": f"{len(unvalidated)} rule(s) used are not validated by a tax professional: "
                                               + ", ".join(unvalidated[:8]) + ". Confirm you accept this to approve.",
                                     "unvalidated": unvalidated, "needs_acknowledgement": True}, status=status.HTTP_409_CONFLICT)
                S.log(eng, request.user, "approved_with_unvalidated_rules", {"stage": stage, "rules": unvalidated})
        S.set_stage(eng, stage, wanted, request.user)
        return _state(request, eng)


class EventsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        eng = _engagement(request, key)
        return Response({"events": [{"id": e.id, "action": e.action, "actor": e.actor, "user": e.user.display_name if e.user_id else "",
                                     "detail": e.detail, "at": e.at} for e in eng.events.select_related("user")[:300]]})


class ExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key, doc, fmt):
        from . import exports

        eng = _engagement(request, key)
        allowed = {"fs": ("pdf", "xlsx", "docx"), "report": ("pdf", "docx"), "computation": ("pdf", "xlsx"), "return": ("pdf", "xlsx"),
                   "journals": ("pdf", "xlsx")}
        if fmt not in allowed.get(doc, ()):
            raise Http404
        st = S.state(eng, request.user)
        try:
            data, name = _document(doc, fmt, eng, st) if doc == "report" or fmt == "docx" else exports.render(doc, fmt, eng, st)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        S.log(eng, request.user, "exported", {"doc": doc, "format": fmt})
        content_type = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[fmt]
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


def _document(doc: str, fmt: str, eng, st: dict) -> tuple[bytes, str]:
    """The report (audit or compilation, its own document) as Word or PDF, and the statements as Word."""
    from . import exports, fs_docx, reports

    e = st["engagement"]
    base = f"{e['legal_name'] or eng.issue.key}"
    if doc == "report":
        if not st.get("report"):
            raise ValueError("The report needs the trial balance first.")
        rep = st["report"]
        title = "Auditor's report" if rep["kind"] == "audit" else "Compilation report"
        if fmt == "docx":
            try:
                return reports.docx(eng, st), f"{base} - {title}.docx"
            except reports.ReportError as exc:
                raise RuntimeError(str(exc)) from exc
        return reports.pdf(eng, st), f"{base} - {title}.pdf"
    fy = f"YA {e['year_of_assessment'].replace('/', '-')}"
    if doc == "fs" and (st.get("financials") or {}).get("kind") == "company":
        try:
            return fs_docx.render(st), f"{base} - Financial statements - {fy}.docx"
        except fs_docx.DocxUnavailable as exc:
            raise RuntimeError(str(exc)) from exc
    title, sections = exports._rows(doc, eng, st)
    return fs_docx.render_sections(title, sections, e), f"{base} - {title} - {fy}.docx"


class AiView(APIView):
    """Local_Tax_AI, the workflow's own agent (LangGraph): it explains, suggests and asks - it never sets a figure."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key, agent):
        eng = _engagement(request, key)
        if agent not in ai.AGENTS:
            raise Http404
        try:
            out = ai.run(agent, eng, S.state(eng, request.user), request.data if isinstance(request.data, dict) else {}, request.user)
        except ai.Unavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ai.Refused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class RulesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, ya=None):
        if ya is None:
            return Response({"years": years()})
        try:
            return Response(load(ya.replace("-", "/")))
        except MissingRules as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class MessagesView(APIView):
    """GET — the engagement's conversation with Local_Tax_AI, oldest first; with the extractions waiting."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        eng = _engagement(request, key)
        return Response({"messages": [ai.message_dict(m) for m in eng.ai_messages.select_related("user")[:200]],
                         "extractions": [ai.extraction_dict(x) for x in eng.extractions.select_related("attachment").order_by("-created_at")[:20]]})


class ExtractionDecideView(APIView):
    """POST {decision: confirm|reject, use_as: trial_balance|income|payments} — a person confirms what the AI read
    from a document before it is used: a trial balance replaces the TB; income and payments are added as lines
    citing the document."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, pk):
        from .models import Extraction

        eng = _engagement(request, key)
        ex = get_object_or_404(Extraction, engagement=eng, pk=pk)
        if ex.status != Extraction.Status.PENDING:
            return Response({"detail": f"Already {ex.status}."}, status=status.HTTP_409_CONFLICT)
        decision = request.data.get("decision")
        if decision == "reject":
            ex.status, ex.decided_by = Extraction.Status.REJECTED, request.user
            ex.save()
            S.log(eng, request.user, "extraction_rejected", {"id": ex.id})
            return _state(request, eng)
        use_as = request.data.get("use_as") or ex.kind
        lines = ex.data.get("lines") or []
        cite = f"{ex.attachment.filename if ex.attachment_id else 'document'}"
        if use_as == "general_ledger":
            # A general ledger: its postings summed by account, by code, into the trial balance.
            by_code: dict = {}
            for ln in lines:
                code = ln["code"] or ln["description"][:40]
                row = by_code.setdefault(code, {"code": code, "name": ln["description"].split(" - ")[0], "amount": Decimal("0")})
                try:
                    row["amount"] += Decimal(ln["amount"] or "0")
                except InvalidOperation:
                    return Response({"lines": [f"{ln['description']}: the amount is not a number."]}, status=status.HTTP_400_BAD_REQUEST)
            try:
                rows = _tb_rows(list(by_code.values()))
            except V.Invalid as exc:
                return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
            _replace_tb(eng, rows, request.user, f"General ledger {cite}, summed by account (confirmed)")
        elif use_as in ("prior_return", "fixed_assets"):
            data = dict(eng.data or {})
            if use_as == "prior_return":
                prior_ya = str(ex.data.get("year_of_assessment") or "")[:9]
                payload = {"prior_year": {"ya": prior_ya, "source": cite, "items": [{"label": ln["description"], "amount": ln["amount"]} for ln in lines]}}
                cf = [ln for ln in lines if ln["category"] == "losses_cf" and ln["amount"]]
                if cf:
                    payload["loss_history"] = (data.get("loss_history") or []) + [
                        {"ya": prior_ya or "Prior year", "amount": ln["amount"], "source": f"{cite} {ln['cite']}".strip()} for ln in cf]
            else:
                payload = {"fixed_assets": (data.get("fixed_assets") or []) + [
                    {"description": ln["description"], "asset_class": ln["category"], "cost": ln["amount"], "acquired": ln.get("date") or "",
                     "ca_claimed_bf": ln["comparative"], "source": f"{cite} {ln['cite']}".strip()} for ln in lines]}
            try:
                _, clean = V.update({"data": payload})
            except V.Invalid as exc:
                return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
            data.update(clean)
            eng.data = data
            S.touch(eng, "questionnaire" if use_as == "prior_return" else "computation", request.user)
            eng.save()
        elif use_as == "comparatives":
            from . import comparatives as CMP
            from . import ppe as PPE

            policy, _ = PPE.policy_for(eng)
            got = CMP.apply(lines, request.data.get("mapping") or ex.data.get("proposals") or [], list(eng.tb_lines.all()), policy)
            for code, amount in got["comparatives"].items():
                TbLine.objects.filter(engagement=eng, code=code).update(comparative=amount.quantize(Decimal("0.01")))
            for n in got["new"]:
                TbLine.objects.create(engagement=eng, code=n["code"], name=n["name"], amount=Decimal("0"), comparative=n["comparative"].quantize(Decimal("0.01")),
                                      heading=n["heading"], heading_by="person")
            cats = got["ppe_categories"]
            if cats["new"] or cats["labels"]:
                # The asset categories are last year's (AFIT, 28 Nov 2026): the client's categories take last year's names
                # and gain last year's classes they lack (rate 0 until the accountant sets it).
                names = cats["labels"]
                rows = [{**c, "label": names.get(c["key"], c["label"])} for c in policy] +                     [{"key": c["key"], "label": c["label"], "method": "straight_line", "rate": "0", "residual": "0"} for c in cats["new"]]
                if PPE.client_of(eng) is not None:
                    PPE.save_policy(eng, rows, request.user)
            data = dict(eng.data or {})
            if cats["labels"]:
                data["ppe"] = {**(data.get("ppe") or {}), "prior_categories": sorted(cats["labels"]),
                               "rate_needed": sorted({c["key"] for c in cats["new"]} | set((data.get("ppe") or {}).get("rate_needed") or []))}
            if got["opening"]:
                ppe = dict(data.get("ppe") or {})
                ppe["opening"] = {**(ppe.get("opening") or {}), **{k: {"cost": str(v["cost"]), "accumulated": str(v["accumulated"]),
                                                                       "source": f"Last year's financial statements ({cite}), PPE note"}
                                                                   for k, v in got["opening"].items()}}
                data["ppe"] = ppe
            if got["tax_rec"]:  # last year's tax reconciliation, as printed: its comparatives
                data["prior_tax_rec"] = {"document": cite, "lines": [{**x, "amount": str(x["amount"])} for x in got["tax_rec"]]}
            if got["revenue_nature"]:  # the revenue note discloses revenue by nature, as last year's statements did
                data["revenue_nature"] = {**(data.get("revenue_nature") or {}), **got["revenue_nature"]}
            if got["cash_flow"]:  # last year's cash flow statement, as printed: this year's cash flow comparatives
                data["prior_cash_flow"] = {"document": cite, "lines": [{**x, "amount": str(x["amount"])} for x in got["cash_flow"]]}
            data["comparatives_source"] = {"document": cite, "at": timezone.now().isoformat(), "by": request.user.display_name,
                                           "accounts": len(got["comparatives"]) + len(got["new"]), "notes": got["notes"]}
            eng.data = data
            S.touch(eng, "fs", request.user)
            eng.save()
        elif use_as in ("ppe_additions", "ppe_disposals"):
            from .engine import depreciation as DEP
            from . import ppe as PPE

            policy, _ = PPE.policy_for(eng)
            data = dict(eng.data or {})
            ppe = dict(data.get("ppe") or {})
            if use_as == "ppe_additions":
                rows = (ppe.get("additions") or []) + [
                    {"description": ln["description"], "category": DEP.category_of(ln["description"], policy), "purchase_date": ln.get("date") or "",
                     "available_date": "", "cost": ln["amount"], "source": f"{cite} {ln['cite']}".strip(), "confirmed": False} for ln in lines if ln["amount"]]
                key = "additions"
            else:
                rows = (ppe.get("disposals") or []) + [
                    {"description": ln["description"], "category": DEP.category_of(ln["description"], policy), "date": ln.get("date") or "",
                     "cost": ln["amount"], "accumulated_bf": "", "proceeds": ln.get("comparative") or "", "source": f"{cite} {ln['cite']}".strip()}
                    for ln in lines if ln["amount"]]
                key = "disposals"
            try:
                _, clean = V.update({"data": {"ppe": {key: rows}}})
            except V.Invalid as exc:
                return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
            ppe[key] = clean["ppe"][key]
            data["ppe"] = ppe
            eng.data = data
            S.touch(eng, "fs", request.user)
            eng.save()
        elif use_as == "trial_balance":
            try:
                rows = _tb_rows([{"code": ln["code"], "name": ln["description"], "amount": ln["amount"], "comparative": ln["comparative"] or None}
                                 for ln in lines])
            except V.Invalid as exc:
                return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
            _replace_tb(eng, rows, request.user, f"AI extraction from {cite} (confirmed)")
        elif use_as in ("income", "payments"):
            data = dict(eng.data or {})
            if use_as == "income":
                add = [{"category": ln["category"] if ln["category"] in S.INCOME_CATEGORIES else "other", "description": ln["description"],
                        "amount": ln["amount"], "source": f"{cite} {ln['cite']}".strip()} for ln in lines]
            else:
                add = [{"type": ln["category"] if ln["category"] in S.PAYMENT_TYPES else "other", "amount": ln["amount"],
                        "reference": (ln["cite"] or cite)[:80]} for ln in lines]
            try:
                _, clean = V.update({"data": {use_as: (data.get(use_as) or []) + add}})
            except V.Invalid as exc:
                return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
            data[use_as] = clean[use_as]
            eng.data = data
            S.touch(eng, "questionnaire", request.user)
            eng.save()
        else:
            return Response({"use_as": ["trial_balance, general_ledger, income, payments, prior_return, fixed_assets, comparatives, ppe_additions "
                                        "or ppe_disposals"]},
                            status=status.HTTP_400_BAD_REQUEST)
        ex.status, ex.decided_by = Extraction.Status.CONFIRMED, request.user
        ex.save()
        S.log(eng, request.user, "extraction_confirmed", {"id": ex.id, "use_as": use_as, "lines": len(lines), "document": cite})
        return _state(request, eng)


# --- Phase 4: the professional review of the rules and the return's field references --------------------------

def _validator(request):
    if not S.can_validate(request.user):
        raise PermissionDenied("Only a tax rule validator (staff or the 'Local tax rule validators' group) can review the rules.")


def _corrected_value(file_value, raw):
    """A corrected value of the same shape as the file's: a number (a rate stays between 0 and 1), or bands
    [[width or null, rate], ...]."""
    if isinstance(file_value, list) or isinstance(raw, list):
        if not isinstance(raw, list) or not raw:
            raise ValueError("Give the bands as [[width, rate], ..., [null, rate]].")
        out = []
        for b in raw:
            if not isinstance(b, (list, tuple)) or len(b) != 2:
                raise ValueError("Each band is [width, rate].")
            try:
                width = None if b[0] in (None, "") else float(b[0])
                rate = float(b[1])
            except (TypeError, ValueError):
                raise ValueError("Each band's width and rate are numbers.") from None
            if not 0 <= rate <= 1:
                raise ValueError("A rate is a fraction between 0 and 1 (0.18 for 18%).")
            out.append([width, rate])
        if out[-1][0] is not None:
            raise ValueError("The last band is the balance: its width is null.")
        return out
    try:
        v = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError("Give a number.") from None
    if v < 0:
        raise ValueError("The value can't be negative.")
    if isinstance(file_value, (int, float)) and file_value < 1 and v > 1:
        raise ValueError("This rule is a rate: give a fraction between 0 and 1 (0.15 for 15%).")
    return v


def _review_register(request, year: str):
    from .models import ReturnFieldReview, RuleReview

    rules = S.rules_for(year)
    history: dict = {}
    for r in RuleReview.objects.filter(year_of_assessment=year).select_related("by"):
        history.setdefault(r.rule, []).append({"status": r.status, "value": r.value, "file_value": r.file_value, "ref": r.ref, "note": r.note,
                                               "active": r.active, "by": r.by.display_name if r.by_id else "", "at": r.at})
    items = [{**r, "history": history.get(r["rule"], [])} for r in rules.all_rules()]
    fields = [{"id": f.id, "entity_type": f.entity_type, "code": f.code, "official": f.official, "note": f.note, "active": f.active,
               "by": f.by.display_name if f.by_id else "", "at": f.at}
              for f in ReturnFieldReview.objects.filter(year_of_assessment=year).select_related("by")]
    return Response({"year_of_assessment": year, "status": rules.data.get("status", ""), "legislation": rules.data.get("legislation", ""),
                     "rules": items, "validated": sum(1 for r in items if r["validated"]), "total": len(items), "fields": fields,
                     "can_validate": S.can_validate(request.user)})


class RuleReviewView(APIView):
    """GET  /api/local-tax/rules/<ya>/review/ - every rule of the year with its review state and history, and the
         return field references checked.
    POST /api/local-tax/rules/<ya>/review/ {rule, action: validate|correct|withdraw, value?, ref, note} - a tax
         professional's review (validators only). Every review is kept; a new one replaces the active one."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, ya):
        try:
            return _review_register(request, ya.replace("-", "/"))
        except MissingRules as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    @transaction.atomic
    def post(self, request, ya):
        from .models import RuleReview

        _validator(request)
        year = ya.replace("-", "/")
        try:
            rules = S.rules_for(year)
        except MissingRules as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        path = str(request.data.get("rule") or "")
        known = {r["rule"]: r for r in rules.all_rules()}
        if path not in known:
            return Response({"rule": ["No such rule for the year."]}, status=status.HTTP_400_BAD_REQUEST)
        action = request.data.get("action")
        ref = " ".join(str(request.data.get("ref") or "").split())[:500]
        note = str(request.data.get("note") or "").strip()[:2000]
        current = RuleReview.objects.filter(year_of_assessment=year, rule=path, active=True)
        if action == "withdraw":
            current.update(active=False)
            return _review_register(request, year)
        if action not in ("validate", "correct"):
            return Response({"action": ["validate, correct or withdraw"]}, status=status.HTTP_400_BAD_REQUEST)
        if len(ref) < 5:
            return Response({"ref": ["Give the legal reference relied on (Act, section, schedule, gazette)."]}, status=status.HTTP_400_BAD_REQUEST)
        file_value = known[path]["file_value"]
        value = file_value
        if action == "correct":
            if not note:
                return Response({"note": ["Say why the value is corrected."]}, status=status.HTTP_400_BAD_REQUEST)
            try:
                value = _corrected_value(file_value, request.data.get("value"))
            except ValueError as exc:
                return Response({"value": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        elif file_value is None:
            return Response({"value": ["This rule has no value in the file: correct it with the value instead."]}, status=status.HTTP_400_BAD_REQUEST)
        current.update(active=False)
        RuleReview.objects.create(year_of_assessment=year, rule=path, status="corrected" if action == "correct" else "validated", value=value,
                                  file_value=file_value, ref=ref, note=note, by=request.user)
        return _review_register(request, year)


class ReturnFieldReviewView(APIView):
    """POST /api/local-tax/rules/<ya>/fields/ {entity_type, code, official, note} - a return field's official RAMIS
    reference (a family of numbered lines as "SCA*"); {.., withdraw: true} withdraws it. Validators only."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, ya):
        import re

        from .models import ReturnFieldReview

        _validator(request)
        year = ya.replace("-", "/")
        if year not in years():
            return Response({"detail": "No rules for that year."}, status=status.HTTP_404_NOT_FOUND)
        entity = request.data.get("entity_type")
        code = str(request.data.get("code") or "").strip().upper()
        if entity not in ("company", "partnership", "individual"):
            return Response({"entity_type": ["company, partnership or individual"]}, status=status.HTTP_400_BAD_REQUEST)
        if not re.fullmatch(r"[A-Z]{1,4}\d{0,3}\*?", code):
            return Response({"code": ["A field code such as C4, or a family such as SCA*."]}, status=status.HTTP_400_BAD_REQUEST)
        current = ReturnFieldReview.objects.filter(year_of_assessment=year, entity_type=entity, code=code, active=True)
        if not request.data.get("withdraw"):
            official = " ".join(str(request.data.get("official") or "").split())[:60]
            if not official:
                return Response({"official": ["Give the field's reference in the RAMIS return."]}, status=status.HTTP_400_BAD_REQUEST)
            current.update(active=False)
            ReturnFieldReview.objects.create(year_of_assessment=year, entity_type=entity, code=code, official=official,
                                             note=str(request.data.get("note") or "")[:500], by=request.user)
        else:
            current.update(active=False)
        return _review_register(request, year)


class RuleCheckView(APIView):
    """POST /api/local-tax/rules/<ya>/review/check/ (multipart: rule, file) - Local_Tax_AI reads the law document
    for the rule and says whether it agrees (validators only). Assistance only: nothing is validated by it."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, ya):
        _validator(request)
        year = ya.replace("-", "/")
        try:
            known = {r["rule"]: r for r in S.rules_for(year).all_rules()}
        except MissingRules as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        rule = known.get(str(request.data.get("rule") or ""))
        f = request.FILES.get("file")
        if rule is None or f is None:
            return Response({"detail": "Choose the rule and the law document."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = ai.rule_check({k: rule[k] for k in ("rule", "label", "value", "ref", "conditions")}, f.name, f.read())
        except ai.Unavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ai.Refused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


# --- client info: supporting documents, the Drive folder and the AI's pre-fill ---------------------------------------

def _docs_response(request, eng, extra: dict | None = None):
    from . import prefill

    eng.refresh_from_db()
    return Response({**prefill.payload(eng), **(extra or {})})


class DocumentsView(APIView):
    """GET /api/local-tax/tasks/<key>/documents/ - the supporting documents (uploads and the Drive folder's copies),
    what Local_Tax_AI suggests from them (each with its sources) and the flags to resolve."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        return _docs_response(request, _engagement(request, key))


class DriveAccountView(APIView):
    """GET /api/local-tax/drive-account/ - the Google account a client's folder is shared with (Viewer)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from . import prefill

        return Response(prefill.drive_account())


class DriveLinkView(APIView):
    """PUT {url} - the client's Google Drive folder, checked that TASKO can open it."""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, key):
        from . import prefill

        eng = _engagement(request, key)
        try:
            listing = prefill.link_drive(eng, str(request.data.get("url") or ""), request.user)
        except ai.Refused as exc:
            return Response({"detail": str(exc), **prefill.drive_account()}, status=status.HTTP_400_BAD_REQUEST)
        except ai.Unavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return _docs_response(request, eng, {"listed": len(listing.get("files") or []), "account_email": listing.get("account_email", "")})


class DriveSyncView(APIView):
    """POST - the Drive folder's new or changed files copied to the task (each read again by the AI)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key):
        from . import prefill

        eng = _engagement(request, key)
        try:
            out = prefill.sync_drive(eng, request.user)
        except ai.Refused as exc:
            return Response({"detail": str(exc), **prefill.drive_account()}, status=status.HTTP_400_BAD_REQUEST)
        except ai.Unavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return _docs_response(request, eng, {"sync": out})


class PrefillView(APIView):
    """The AI pre-fill, a document at a time so the screen shows progress:
    POST .../prefill/start/ {again?} -> {documents: [ids to read]}
    POST .../prefill/read/ {document_id} -> that document's reading
    POST .../prefill/finish/ -> suggestions and flags from every document's reading."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key, step):
        from . import prefill
        from .models import SourceDocument

        eng = _engagement(request, key)
        if step == "start":
            return Response({"documents": prefill.to_read(eng, again=bool(request.data.get("again")))})
        if step == "read":
            doc = get_object_or_404(SourceDocument.objects.select_related("attachment"), engagement=eng, pk=request.data.get("document_id"))
            try:
                doc = prefill.read_document(eng, doc)
            except ai.Unavailable as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({"document": prefill.document_dict(doc)})
        if step == "finish":
            with transaction.atomic():
                return Response(prefill.finish(eng, request.user))
        raise Http404


class SuggestionDecideView(APIView):
    """POST {decision: confirm|reject, value?} - the accountant confirms (as it is, or edited) or rejects a value the AI
    found; a confirmed one is written to the client info with its source."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, pk):
        from . import prefill
        from .models import Suggestion

        eng = _engagement(request, key)
        sug = get_object_or_404(Suggestion, engagement=eng, pk=pk)
        if sug.status != Suggestion.Status.PENDING:
            return Response({"detail": f"Already {sug.get_status_display().lower()}."}, status=status.HTTP_409_CONFLICT)
        decision = request.data.get("decision")
        if decision not in ("confirm", "reject"):
            return Response({"decision": ["confirm or reject"]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            prefill.decide(eng, sug, decision, request.user, request.data.get("value") if "value" in request.data else None)
        except V.Invalid as exc:
            transaction.set_rollback(True)
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        eng.refresh_from_db()
        return Response({"state": S.state(eng, request.user), **prefill.payload(eng)})


class FlagResolveView(APIView):
    """POST {resolution} - the accountant says how a flag was resolved (kept in the audit trail)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key, pk):
        from . import prefill
        from .models import Flag

        eng = _engagement(request, key)
        f = get_object_or_404(Flag, engagement=eng, pk=pk)
        text = " ".join(str(request.data.get("resolution") or "").split())
        if len(text) < 3:
            return Response({"resolution": ["Say how it was resolved."]}, status=status.HTTP_400_BAD_REQUEST)
        prefill.resolve(eng, f, text, request.user)
        return _docs_response(request, eng)


# --- PPE & depreciation, prior-year comparatives (AFIT, 24 Nov 2026) -------------------------------------------------

class PpePolicyView(APIView):
    """PUT {policy: [{key, label, method, rate, residual}]} - the client's depreciation policy, kept with the client
    for every later year."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, key):
        from . import ppe as PPE

        eng = _engagement(request, key)
        try:
            PPE.save_policy(eng, request.data.get("policy"), request.user)
        except V.Invalid as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        return _state(request, eng)


class PpeApproveView(APIView):
    """POST - the depreciation schedule approved: the depreciation journal (JE-DEP) posted or replaced."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        from . import ppe as PPE

        eng = _engagement(request, key)
        if not S.can_approve(request.user, eng.issue):
            raise PermissionDenied("Only a reviewer, a lead or an admin can approve the depreciation.")
        try:
            PPE.approve(eng, request.user)
        except PPE.NotReady as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return _state(request, eng)


class PriorFsView(APIView):
    """POST {link} or {attachment_id} - last year's financial statements read by Local_Tax_AI for this year's
    comparatives: the lines read, each with the trial balance account code proposes. Nothing changes until the
    accountant confirms (extractions/<id>/decide/ with use_as "comparatives" and the mapping)."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        import base64

        from django.core.files.base import ContentFile

        from . import comparatives as CMP
        from .models import Extraction

        eng = _engagement(request, key)
        if not eng.tb_lines.exists():
            return Response({"detail": "Load this year's trial balance first: the comparatives are matched to its accounts."},
                            status=status.HTTP_400_BAD_REQUEST)
        att_id = request.data.get("attachment_id")
        link = str(request.data.get("link") or "").strip()
        try:
            if not att_id:
                file_id = CMP.file_id_from(link)
                if not file_id:
                    return Response({"link": ["Paste the Google Drive link to last year's financial statements (https://drive.google.com/file/d/...)."]},
                                    status=status.HTTP_400_BAD_REQUEST)
                got = ai._call("/v1/drive/download", {"file_id": file_id}, timeout=180)
                att = Attachment.objects.create(issue=eng.issue, file=ContentFile(base64.b64decode(got["content_b64"]), name=got["name"][:200]),
                                                filename=got["name"][:255], uploaded_by=request.user)
                att_id = att.id
                S.log(eng, request.user, "prior_fs_downloaded", {"link": link[:500], "document": got["name"][:255]})
            out = ai.run("extract", eng, S.state(eng, request.user), {"attachment_id": att_id, "kind": "prior_fs"}, request.user)
        except ai.Refused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ai.Unavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        ex = Extraction.objects.get(pk=out["extraction"]["id"])
        ex.kind = "prior_fs"
        ex.data = {**ex.data, "proposals": CMP.propose(ex.data.get("lines") or [], S.tb_lines(eng)), "link": link[:500]}
        ex.save()
        return Response({"extraction": ai.extraction_dict(ex), "state": S.state(eng, request.user)})


class ClientChangeView(APIView):
    """POST {decision: apply|dismiss} — a change the client asked for, proposed by Local_Tax_AI in the chat (AFIT,
    26 Nov 2026), applied by the accountant: client information, a note's or a policy's wording and an account's heading
    change at once (as if edited by hand); a journal or a tax adjustment is PROPOSED, to be approved like any other. The
    change is checked again first: a journal whose accounts' balances have moved since is worked out again and shown
    (409) for the accountant to check before applying."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key, pk, n):
        eng = _engagement(request, key)
        msg = get_object_or_404(AiMessage.objects.select_for_update(), engagement=eng, pk=pk, role="ai")
        changes = list((msg.data or {}).get("changes") or [])
        if not 0 <= n < len(changes):
            raise Http404
        change = dict(changes[n])
        if change.get("status") != "proposed":
            return Response({"detail": f"Already {change.get('status')}."}, status=status.HTTP_409_CONFLICT)
        decision = request.data.get("decision")
        if decision not in ("apply", "dismiss"):
            return Response({"decision": ["apply or dismiss"]}, status=status.HTTP_400_BAD_REQUEST)

        def save(**updates):
            changes[n] = {**change, **updates, "by": request.user.display_name, "at": timezone.now().isoformat()}
            msg.data = {**msg.data, "changes": changes}
            msg.save(update_fields=["data"])

        if decision == "dismiss":
            save(status="dismissed")
            S.log(eng, request.user, "client_change_dismissed", {"message": msg.id, "change": n, "label": change.get("label")})
            return _state(request, eng)
        st = S.state(eng, request.user)
        try:
            fresh = CR.check(eng, st, change, S.financials(eng))
        except ValueError as exc:
            return Response({"detail": f"This change can't be made now: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        if change["type"] == "journal" and fresh["lines"] != change.get("lines"):
            changes[n] = {**change, "lines": fresh["lines"]}
            msg.data = {**msg.data, "changes": changes}
            msg.save(update_fields=["data"])
            return Response({"detail": "The accounts' balances have changed since this was proposed: the journal has been worked out again. "
                                       "Check it and apply."}, status=status.HTTP_409_CONFLICT)
        why = f"Client request (via the AI Assistant): {change.get('reason') or ''}".strip()
        kind, target, value = change["type"], change["target"], change["value"]
        try:
            if kind == "field":
                _edit(eng, request.user, {**CR.field_payload(target, value), "reason": why})
                result = f"{fresh['label']} changed."
            elif kind == "note":
                texts = {**((eng.data or {}).get("note_text") or {}), target: value}
                _edit(eng, request.user, {"data": {"note_text": texts}, "stage": "fs", "reason": why})
                result = "Note wording changed."
            elif kind == "policy":
                texts = {**((eng.data or {}).get("policy_text") or {}), target: value}
                _edit(eng, request.user, {"data": {"policy_text": texts}, "stage": "fs", "reason": why})
                result = "Policy wording changed."
            elif kind == "heading":
                line = eng.tb_lines.get(code=target)
                old = line.heading
                line.heading, line.heading_by, line.heading_note = fresh["heading"], "person", why[:300]
                line.save()
                S.touch(eng, "fs", request.user)
                eng.save()
                S.log(eng, request.user, "mapping", {"code": target, "from": old, "to": fresh["heading"], "reason": why})
                result = f"Account {target} now shown under {fresh['to']}."
            else:
                data = ({"kind": "journal", "label": change["label"], "lines": fresh["lines"], "reason": why}
                        if kind == "journal" else {"kind": "tax", "target": target, "proposed": fresh["to"], "label": fresh["label"], "reason": why})
                fields, errors = _adjustment_fields(eng, data, st.get("levers") or [])
                if errors:
                    return Response({"detail": "This change can't be made now: " + "; ".join(str(v) for v in errors.values())},
                                    status=status.HTTP_400_BAD_REQUEST)
                adj = _propose(eng, request.user, fields)
                result = (f"{adj.ref} proposed: it changes the statements once approved in Journal Entries." if kind == "journal"
                          else "Tax adjustment proposed: it changes the computation once approved.")
        except V.Invalid as exc:
            return Response({"detail": "This change can't be made now: " + "; ".join(str(v) for v in exc.errors.values())},
                            status=status.HTTP_400_BAD_REQUEST)
        save(status="applied", result=result)
        S.log(eng, request.user, "client_change_applied", {"message": msg.id, "change": n, "type": kind, "label": change.get("label"), "result": result})
        return _state(request, eng)


class FsEditView(APIView):
    """POST {heading, value} — a line of the statements shown at a new figure (AFIT, 26 Nov 2026); never a total.
    DELETE {heading?} — that edit (or every edit) undone. The statements show the edit at once and are flagged until the
    edits balance (fs_edits.py)."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        from . import fs_edits as FE

        eng = _engagement(request, key)
        base = S.financials(eng, with_edits=False)
        if not base or base.get("kind") != "company":
            return Response({"detail": "Statement figures are edited once there is a trial balance."}, status=status.HTTP_400_BAD_REQUEST)
        heading = request.data.get("heading")
        try:
            out = FE.set_edit(eng, request.user, heading, request.data.get("value"), base["lines"])
        except ValueError as exc:
            return Response({"value": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        S.touch(eng, "fs", request.user)
        eng.save()
        S.log(eng, request.user, "fs_edited", {"heading": heading, "edit": out["item"], "withdrew": out["replaced"]})
        return _state(request, eng)

    @transaction.atomic
    def delete(self, request, key):
        from . import fs_edits as FE

        eng = _engagement(request, key)
        heading = request.data.get("heading") if isinstance(request.data, dict) else None
        FE.clear(eng, heading or None)
        S.touch(eng, "fs", request.user)
        eng.save()
        S.log(eng, request.user, "fs_edit_undone", {"heading": heading or "all"})
        return _state(request, eng)


class FsEditsPostView(APIView):
    """POST — the statement edits, once they balance, posted to the trial balance: Local_Tax_AI chooses the account under
    each heading (code falls back to the largest), and one journal is proposed, approved like any other. Approving it
    clears the edits - the trial balance carries them from then on."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        from . import fs_edits as FE

        eng = _engagement(request, key)
        full = S.fs_scope(eng) == "full"
        summary = FE.summary(eng, full)
        if not summary or not summary["items"]:
            return Response({"detail": "No statement figures have been edited."}, status=status.HTTP_400_BAD_REQUEST)
        if not summary["balanced"]:
            return Response({"detail": f"The edits are out of balance by {Decimal(summary['difference']):,.2f}: edit the other side first."},
                            status=status.HTTP_409_CONFLICT)
        if not summary["can_post"]:
            return Response({"detail": "The edits are already in a journal waiting for approval."}, status=status.HTTP_409_CONFLICT)
        base = S.financials(eng, with_edits=False)
        picks, notes = ai.pick_accounts(eng, base["lines"])
        lines, more = FE.journal_lines(eng, base["lines"], picks, full)
        labels = ", ".join(i["label"] for i in summary["items"])
        fields, errors = _adjustment_fields(eng, {"kind": "journal", "label": "Statement edits posted to the trial balance", "lines": lines,
                                                  "reason": f"Figures edited on the statements ({labels}); accounts chosen by Local_Tax_AI."}, [])
        if errors:
            return Response({"detail": "; ".join(str(v) for v in errors.values())}, status=status.HTTP_400_BAD_REQUEST)
        fields["target"] = FE.AUTO
        adj = _propose(eng, request.user, fields)
        edits = FE.stored(eng)
        eng.data = {**(eng.data or {}), "fs_edits": {**edits, "journal": adj.id, "notes": notes + more}}
        eng.save()
        S.log(eng, request.user, "fs_edits_posted", {"journal": adj.ref, "lines": len(lines)})
        return _state(request, eng)


class UpdateView(APIView):
    """POST {stage} — Update (AFIT, 26 Nov 2026): the workflow worked out again from everything entered - the statements,
    depreciation, the computation and the return - with what changed since the last update."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, key):
        eng = _engagement(request, key)
        st = S.state(eng, request.user)
        now = S.key_figures(st)
        last = (eng.data or {}).get("last_update") or {}
        before = last.get("figures") or {}
        changes = [{"key": k, "label": label, "from": before.get(k), "to": now.get(k)} for k, label in S.KEY_FIGURES
                   if before and before.get(k) != now.get(k)]
        stage = request.data.get("stage") if request.data.get("stage") in TaxEngagement.STAGES else ""
        at = timezone.now().isoformat()
        eng.data = {**(eng.data or {}), "last_update": {"at": at, "by": request.user.display_name, "stage": stage, "figures": now}}
        eng.save(update_fields=["data", "updated_at"])
        S.log(eng, request.user, "updated", {"stage": stage, "changes": changes})
        return Response({"state": S.state(eng, request.user), "changes": changes, "first": not before, "at": at})
