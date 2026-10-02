"""Emails in a job folder: .eml files and Outlook .msg files. Read by code, never by a model.

An email becomes a document of its own (who, when, subject, then the body line by line), and
each file attached to it becomes another document, exactly like a file inside a zip:
"Invoice.pdf (attached to RE Year end query.eml)". Small pictures embedded in the body
(signature logos) are left out, so nobody pays to have a logo read.
"""
import email
import email.policy
import html
import io
import re

EMAIL_EXTS = ("eml", "msg")
EMAIL_MIMES = ("message/rfc822", "application/vnd.ms-outlook")
MAX_BODY_LINES = 600


def is_email(name: str, mime_type: str = "") -> bool:
    return name.lower().rsplit(".", 1)[-1] in EMAIL_EXTS or mime_type in EMAIL_MIMES


def html_to_text(markup: str) -> str:
    """Readable lines from HTML, with table cells kept on one line. No library needed."""
    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", markup)
    text = re.sub(r"(?i)</t[dh]\s*>", " | ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table|blockquote)\s*>", "\n", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "", text))
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip(" |") for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _safe_name(name: str, fallback: str) -> str:
    name = re.sub(r"[\\/!\r\n\t]+", " ", name or "").strip()
    return name[:120] or fallback


def _leaves(part):
    """Every part of an email that is not a container, without going inside a forwarded email."""
    if part.get_content_type() == "message/rfc822" or not part.is_multipart():
        yield part
        return
    for sub in part.iter_parts():
        yield from _leaves(sub)


def _read_eml(data: bytes) -> dict:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    headers = [(label, str(msg[label])) for label in ("From", "To", "Cc", "Date", "Subject") if msg[label]]
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        content = body_part.get_content()
        body = html_to_text(content) if body_part.get_content_type() == "text/html" else content
    attachments = []
    for n, part in enumerate(_leaves(msg), start=1):
        if part is body_part:
            continue
        if part.get_content_type() == "message/rfc822":  # a forwarded email, attached whole
            inner = part.get_content()
            attachments.append((_safe_name(str(inner["Subject"] or ""), f"forwarded email {n}") + ".eml", inner.as_bytes(), False))
            continue
        if part.get_content_maintype() == "text" and not part.get_filename():
            continue  # the other form of the body (HTML beside plain text)
        content = part.get_payload(decode=True) or b""
        ext = (part.get_content_subtype() or "bin").split("+")[0]
        inline = part.get_content_maintype() == "image" and (bool(part["Content-ID"]) or part.get_content_disposition() != "attachment")
        attachments.append((_safe_name(part.get_filename(), f"attachment {n}.{ext}"), content, inline))
    return {"headers": headers, "body": body, "attachments": attachments}


def _read_msg(data: bytes) -> dict:
    import extract_msg

    msg = extract_msg.openMsg(io.BytesIO(data))
    try:
        values = (("From", msg.sender), ("To", msg.to), ("Cc", msg.cc), ("Date", msg.date), ("Subject", msg.subject))
        headers = [(label, str(value)) for label, value in values if value]
        body = msg.body or ""
        if not body.strip() and getattr(msg, "htmlBody", None):
            raw = msg.htmlBody
            body = html_to_text(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
        attachments = []
        for n, att in enumerate(msg.attachments, start=1):
            content = att.data
            name = _safe_name(att.getFilename() if hasattr(att, "getFilename") else getattr(att, "longFilename", ""), f"attachment {n}")
            if not isinstance(content, bytes):  # an Outlook message attached to this one
                export = getattr(content, "exportBytes", None)
                if export is None:
                    continue
                content, name = export(), (name if name.lower().endswith(".msg") else name + ".msg")
            inline = bool(getattr(att, "cid", None)) and name.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "bmp")
            attachments.append((name, content, inline))
        return {"headers": headers, "body": body, "attachments": attachments}
    finally:
        msg.close()


def read_email(data: bytes, name: str) -> dict:
    """{"headers": [(label, value)], "body": text, "attachments": [(name, bytes, inline)]}.
    Raises on a file that is not an email."""
    if name.lower().endswith(".msg") or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return _read_msg(data)
    return _read_eml(data)


def email_lines(mail: dict) -> list[str]:
    """The email as numbered-able lines: the headers, what is attached, then the body."""
    lines = [label + ": " + re.sub(r"\s+", " ", value).strip() for label, value in mail["headers"]]
    named = [name for name, _, inline in mail["attachments"] if not inline]
    if named:
        lines.append("Attachments: " + ", ".join(named))
    for line in mail["body"].splitlines()[:MAX_BODY_LINES]:
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines
