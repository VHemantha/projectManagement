"""The practitioner's report on the financial statements (AFIT, 26 Nov 2026): the independent auditor's report or the
compilation report, chosen with the client details, in the firm's own formats (local-tax-ai/reports_formats, copied to
assets/report_templates). A separate document from the financial statements.

Each paragraph of the format is a section with a key; its wording is filled in from the engagement (the entity's
name, the year end, the framework, profit or loss) and may be edited by the accountant (data.report_text, by key; ""
goes back to the format's wording). The Word file is the firm's template itself with the paragraphs filled in - the
letterhead, fonts and page set-up are the template's; the PDF is drawn to the same layout.
"""
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

ASSETS = Path(__file__).resolve().parent / "assets"
TEMPLATES = {"audit": ASSETS / "report_templates" / "audit.docx", "compilation": ASSETS / "report_templates" / "compilation.docx"}
LOGO = ASSETS / "afit_logo.png"

FRAMEWORK = {"full": "Sri Lanka Accounting Standards (SLFRSs and LKASs)",
             "smes": "Sri Lanka Accounting Standard for Small and Medium-Sized Entities (SLFRS for SMEs)",
             "smaller": "Sri Lanka Accounting Standard for Smaller Entities (SLASSE)"}
NOUN = {"company": "Company", "partnership": "Partnership", "individual": "Business"}
FOOTER = [("AFIT Connect (Chartered Accountants)", True),
          ("P.O. Box – 58/8/H, Ihala Karagahamuna, Kadawatha, Gampaha, Sri Lanka", False),
          ("Tel - +94 11 292 99 49, +94 11 365 27 91 , +94 77 125 30 35", False),
          ("Email – info@afitconnect.com  Web - www.afitconnect.com", False),
          ("Practitioner – Dushan Thumbovila (FCA, ACCA, BSc) Director – Nuwan Srimal (ACA, ACCA, BSc)", False)]
SIGNATURE = ("AFIT CONNECT", "CHARTERED ACCOUNTANTS", "GAMPAHA, SRI LANKA")

# The paragraphs of each format, in order: (key, kind, how the template's paragraph starts). "kind": title |
# addressee | heading | para | sign | date. The matching is on the start of the template's own text.
AUDIT_LAYOUT = [
    ("title", "title", "independent auditor"),
    ("addressee", "addressee", "to shareholders of"),
    ("h_report", "heading", "report on the financial statements"),
    ("intro", "para", "we have audited"),
    ("h_management", "heading", "management"),
    ("management", "para", "management is responsible"),
    ("h_scope", "heading", "scope of audit"),
    ("scope", "para", "our responsibility is"),
    ("scope_basis", "para", "we have obtained all"),
    ("h_opinion", "heading", "opinion"),
    ("opinion", "para", "in our opinion"),
    ("h_legal", "heading", "report on other legal"),
    ("legal", "para", "these financial statements also comply"),
]
COMPILATION_LAYOUT = [
    ("title", "title", "compilation repor"),
    ("body", "para", "on the basis of information"),
]


class ReportError(ValueError):
    pass


def kind_of(eng) -> str:
    return "audit" if eng.audited else "compilation"


def _long(d: date | None) -> str:
    return f"{d.day} {d.strftime('%B %Y')}" if d else "[year end]"


def _us(d: date | None) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}" if d else "[year end]"


def report_date(eng) -> date:
    raw = (eng.data or {}).get("report_date")
    try:
        return date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        return date.today()


def _defaults(eng, st: dict) -> dict[str, str]:
    """Each section's wording in the firm's format, filled in for this engagement."""
    e = eng
    name = (e.legal_name or e.client_name or "[Entity]").strip()
    entity = e.entity_type if e.entity_type in NOUN else "company"
    noun = NOUN[entity]
    ye = _long(e.fy_end)
    framework = FRAMEWORK.get(e.reporting_framework or "smes", FRAMEWORK["smes"])
    fin = st.get("financials") or {}
    profit = Decimal(str(fin.get("profit") or 0)) if fin else Decimal(0)
    result = "profit" if profit >= 0 else "loss"
    income_only = ((e.data or {}).get("fs_scope") or "full") == "income_statement"
    owner = ((e.data or {}).get("directors") or "").strip() or "[Proprietor's full name]"
    if kind_of(eng) == "audit":
        addressee = {"company": f"To Shareholders of {name}.", "partnership": f"To the Partners of {name}.",
                     "individual": f"To {owner}, trading as {name}."}[entity]
        statements = ("the income statement for the year then ended" if income_only else
                      f"the balance sheet as at {ye}, and the income statement, statement of changes in equity and cash flow statement for the "
                      "year then ended")
        if income_only:
            intro = (f"We have audited the accompanying income statement of {name} (the {noun}) for the year ended {ye}, and a summary of "
                     "significant accounting policies and other explanatory notes.")
            view = f"the income statement gives a true and fair view of the {noun}'s {result} for the year then ended"
        else:
            intro = (f"We have audited the accompanying financial statements of {name} (the {noun}), which comprise {statements}, and a "
                     "summary of significant accounting policies and other explanatory notes.")
            view = (f"the financial statements give a true and fair view of the {noun}'s state of affairs as at {ye} and its {result} and cash "
                    "flows for the year then ended")
        out = {
            "title": "INDEPENDENT AUDITOR’S REPORT",
            "addressee": addressee,
            "h_report": "Report on the Financial Statements",
            "intro": intro,
            "h_management": "Management’s Responsibility for the Financial Statements",
            "management": ("Management is responsible for the preparation and fair presentation of these financial statements in accordance with "
                           f"{framework}. This responsibility includes designing, implementing and maintaining internal control relevant to the "
                           "preparation and fair presentation of financial statements that are free from material misstatement, whether due to fraud "
                           "or error. It also includes selecting and applying appropriate accounting policies and making accounting estimates that "
                           "are reasonable in the circumstances."),
            "h_scope": "Scope of Audit and Basis of Opinion",
            "scope": ("Our responsibility is to express an opinion on these financial statements based on our audit. We conducted our audit in "
                      "accordance with Sri Lanka Auditing Standards. Those standards require that we plan and perform the audit to obtain "
                      "reasonable assurance whether the financial statements are free from material misstatement. An audit includes examining, on "
                      "a test basis, evidence supporting the amounts and disclosures in the financial statements. An audit also includes assessing "
                      "the accounting policies used and significant estimates made by management, as well as evaluating the overall financial "
                      "statement presentation."),
            "scope_basis": ("We have obtained all the information and explanations which to the best of our knowledge and belief were necessary "
                            "for the purposes of our audit. We therefore believe that our audit provides a reasonable basis for our opinion."),
            "h_opinion": "Opinion",
            "opinion": (f"In our opinion, so far as appears from our examination, the {noun} maintained proper accounting records for the year "
                        f"ended {ye} and {view} in accordance with {framework}."),
        }
        if entity == "company":
            out.update({"h_legal": "Report on Other Legal and Regulatory Requirements",
                        "legal": "These financial statements also comply with the requirements of the applicable provisions of the Companies Act "
                                 "No. 07 of 2007 set out below."})
        return out
    title = {"company": f"COMPILATION REPORT TO THE SHAREHOLDERS OF {name.upper()}",
             "partnership": f"COMPILATION REPORT TO THE PARTNERS OF {name.upper()}",
             "individual": f"COMPILATION REPORT TO {owner.upper()}, TRADING AS {name.upper()}"}[entity]
    what = (f"the statement of income of {name} for the year ended {_us(e.fy_end)}" if income_only else
            f"the balance sheet of {name} as of {_us(e.fy_end)} and statements of income and cash flows for the year then ended")
    return {"title": title,
            "body": ("On the basis of information provided by management we have compiled, in accordance with the Sri Lanka Standard on Related "
                     f"Services applicable to compilation engagements, {what}. Management is responsible for these financial statements. We "
                     "have not audited or reviewed these financial statements and accordingly express no assurance thereon.")}


def report(eng, st: dict) -> dict:
    """The report as the screen shows and edits it: {kind, title, date, sections: [{key, kind, text, standard, edited}], signature}."""
    kind = kind_of(eng)
    layout = AUDIT_LAYOUT if kind == "audit" else COMPILATION_LAYOUT
    defaults = _defaults(eng, st)
    edited = ((eng.data or {}).get("report_text") or {}).get(kind) or {}
    sections = []
    for key, k, _ in layout:
        if key not in defaults:
            continue
        text = edited.get(key) or defaults[key]
        sections.append({"key": key, "kind": k, "text": text, "standard": defaults[key], "edited": bool(edited.get(key))})
    when = report_date(eng)
    return {"kind": kind, "label": "Independent auditor's report" if kind == "audit" else "Compilation report",
            "date": when.isoformat(), "date_text": _long(when), "sections": sections, "signature": list(SIGNATURE),
            "draft_note": ("A draft for the engagement partner: the opinion is the auditor's to give, after the audit." if kind == "audit"
                           else "Issued on the firm's compilation engagement (SLSRS 4410): no assurance is expressed.")}


# --- the Word file: the firm's template, filled in ---------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("‘", "'")).strip().lower()


def _set_text(p, text: str) -> None:
    """A paragraph's words replaced, keeping its first run's formatting (font, size, bold)."""
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def _drop(p) -> None:
    p._p.getparent().remove(p._p)


def docx(eng, st: dict) -> bytes:
    try:
        import docx as python_docx
    except ImportError as exc:  # installed on deploy (requirements.txt)
        raise ReportError("Word files can't be made on this server yet.") from exc
    rep = report(eng, st)
    layout = AUDIT_LAYOUT if rep["kind"] == "audit" else COMPILATION_LAYOUT
    texts = {s["key"]: s["text"] for s in rep["sections"]}
    doc = python_docx.Document(str(TEMPLATES[rep["kind"]]))
    paragraphs = list(doc.paragraphs)
    used = set()
    for n, p in enumerate(paragraphs):
        t = _norm(p.text)
        if not t:
            continue
        if t == "{today}":
            _set_text(p, rep["date_text"])
            continue
        for key, _, start in layout:
            if key in used or not t.startswith(start):
                continue
            used.add(key)
            if key in texts:
                _set_text(p, texts[key])
            else:
                _drop(p)  # e.g. the Companies Act paragraph for a partnership
            if rep["kind"] == "compilation" and key == "body":
                # the format breaks its one sentence across two paragraphs: the whole sentence goes in the first
                nxt = paragraphs[n + 1] if n + 1 < len(paragraphs) else None
                if nxt is not None and _norm(nxt.text).startswith("accordingly"):
                    _drop(nxt)
            break
    buf = io.BytesIO()
    doc.core_properties.title = rep["label"]
    doc.save(buf)
    return buf.getvalue()


# --- the PDF: the same layout ------------------------------------------------------------------------------------

def pdf(eng, st: dict) -> bytes:
    from reportlab.lib.colors import HexColor, black
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    rep = report(eng, st)
    serif, bold = "Times-Roman", "Times-Bold"
    body = ParagraphStyle("body", fontName=serif, fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceAfter=8)
    styles = {
        "title": ParagraphStyle("title", parent=body, fontName=serif, fontSize=16, leading=20, spaceAfter=14,
                                alignment=TA_LEFT if rep["kind"] == "audit" else TA_JUSTIFY),
        "addressee": ParagraphStyle("addr", parent=body, fontSize=12, spaceAfter=12),
        "heading": ParagraphStyle("h", parent=body, fontName=bold, fontSize=12, spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "para": body,
    }
    if rep["kind"] == "compilation":
        styles["title"] = ParagraphStyle("ct", parent=body, fontName=bold, fontSize=11, spaceBefore=14, spaceAfter=24)
    story = []
    for s in rep["sections"]:
        style = styles.get(s["kind"], body)
        story.append(Paragraph(escape(s["text"]).replace("\n", "<br/>"), style))
    story.append(Spacer(1, 30))
    sign = ParagraphStyle("sign", parent=body, fontName=bold, alignment=TA_LEFT, spaceAfter=0)
    story += [Paragraph(SIGNATURE[0], sign), Paragraph(SIGNATURE[1], sign), Spacer(1, 12), Paragraph(SIGNATURE[2], sign), Spacer(1, 12),
              Paragraph(escape(rep["date_text"]), sign)]

    def page(canvas, doc):
        canvas.saveState()
        w, h = letter
        if LOGO.exists():
            canvas.drawImage(str(LOGO), 2.5 * cm, h - 2.5 * cm + 0.2 * cm, width=4.39 * cm, height=1.63 * cm, preserveAspectRatio=True, mask="auto")
        y = 2.2 * cm
        canvas.setStrokeColor(HexColor("#C00000"))
        canvas.setLineWidth(1)
        canvas.line(2.5 * cm, y + 0.45 * cm, w - 2.0 * cm, y + 0.45 * cm)
        canvas.setFillColor(black)
        for text, is_bold in FOOTER:
            canvas.setFont("Times-Bold" if is_bold else "Times-Roman", 8)
            canvas.drawString(2.5 * cm, y, text)
            y -= 0.36 * cm
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2.5 * cm, rightMargin=2.0 * cm, topMargin=2.5 * cm + 1.2 * cm, bottomMargin=2.5 * cm + 1.0 * cm,
                            title=rep["label"], author="AFIT Connect")
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
