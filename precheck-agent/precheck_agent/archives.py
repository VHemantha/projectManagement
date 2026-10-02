"""Files that hold other files: zip archives and emails with attachments.

Some job folders hold one zip with the documents inside. The archive is opened in memory and
each file inside becomes its own document, exactly as if it sat in the folder: it is parsed,
classified, indexed and cited on its own ("Trial Balance.xlsx (in Documents.zip)").

A member's id is "<zip file id>!<path inside the zip>" and its version is the CRC and size of
its content, so re-uploading the zip with one file changed re-reads only that file.

An email is handled the same way: the email is a document, and each file attached to it is a
document of its own ("Invoice.pdf (attached to RE Year end.eml)"), with the id
"<email id>!<attachment name>". Emails inside zips, and zips attached to emails, both work.
"""
import io
import zipfile
import zlib

from .config import Settings
from .emails import is_email, read_email

SEP = "!"
MAX_DEPTH = 3  # e.g. a zip, an email in it, a zip attached to that email; deeper is not opened


def container_of(file_id: str) -> str:
    """The id of the Drive file a document came from (itself, unless it is inside a zip)."""
    return file_id.split(SEP, 1)[0]


def display_name(file: dict) -> str:
    """"Trial Balance.xlsx (in Documents.zip)" for a document inside a zip, "Invoice.pdf
    (attached to Query.eml)" for an email attachment, else its name."""
    parts = (file.get("path") or "").split("/")
    for part in reversed(parts):
        if is_email(part):
            return f"{file['name']} (attached to {part})"
    for part in parts:
        if part.lower().endswith(".zip"):
            return f"{file['name']} (in {part})"
    return file["name"]


def _skip(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    return not base or base.startswith((".", "~$")) or name.startswith("__MACOSX/") or base in ("Thumbs.db", "desktop.ini")


def members(data: bytes, zip_file: dict, settings: Settings, depth: int = 1) -> tuple[list[dict], str]:
    """(documents inside the archive, problem). Each document is a file dict like a Drive
    listing entry plus "data" (its bytes) or "error" (why it was not read)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [], "This zip file could not be opened."
    out: list[dict] = []
    budget = settings.max_zip_bytes * 3  # total uncompressed size we are willing to hold
    for info in archive.infolist():
        if info.is_dir() or _skip(info.filename):
            continue
        if len(out) >= settings.max_zip_members:
            return out, f"Only the first {settings.max_zip_members} files in this zip were read."
        base = info.filename.rsplit("/", 1)[-1]
        inner_dir = info.filename[: -len(base)]
        doc = {
            "id": f"{zip_file['id']}{SEP}{info.filename}",
            "name": base,
            "mime_type": "",
            "version": f"{info.CRC:08x}-{info.file_size}",
            "modified_time": zip_file.get("modified_time", ""),
            "size": info.file_size,
            "web_url": zip_file["web_url"],  # Drive cannot link inside a zip: the link opens the zip
            "path": f"{zip_file.get('path', '')}{zip_file['name']}/{inner_dir}",
            "archive": zip_file["name"],
        }
        if info.flag_bits & 0x1:
            out.append({**doc, "error": "This file is password-protected inside the zip."})
            continue
        if info.file_size > settings.max_file_bytes or info.file_size > budget:
            out.append({**doc, "error": "This file is too large to read."})
            continue
        budget -= info.file_size
        content = archive.read(info)
        out.extend(_expand(doc, content, settings, depth))
    return out, ""


def _expand(doc: dict, content: bytes, settings: Settings, depth: int) -> list[dict]:
    """One file found inside a zip or an email: itself, or what it holds when it is a zip or
    an email with attachments."""
    name = doc["name"].lower()
    if name.endswith(".zip"):
        if depth >= MAX_DEPTH:
            return [{**doc, "error": "This zip is nested too deeply to open."}]
        inner, problem = members(content, doc, settings, depth + 1)
        return inner + ([{**doc, "error": problem}] if problem else [])
    if is_email(name) and depth < MAX_DEPTH:
        return [{**doc, "data": content}] + attachments(content, doc, settings, depth + 1)
    return [{**doc, "data": content}]


def attachments(data: bytes, email_file: dict, settings: Settings, depth: int = 1) -> list[dict]:
    """The files attached to an email, as documents of their own. Small pictures embedded in
    the body (signature logos) are left out. An email that cannot be opened has none: the
    parser reports the problem on the email itself."""
    try:
        mail = read_email(data, email_file["name"])
    except Exception:
        return []
    out, seen = [], set()
    for name, content, inline in mail["attachments"][: settings.max_zip_members]:
        if inline and len(content) < settings.min_inline_image_bytes:
            continue
        key = name
        while key in seen:  # two attachments with one name stay two documents
            key += "~"
        seen.add(key)
        doc = {
            "id": f"{email_file['id']}{SEP}{key}",
            "name": name,
            "mime_type": "",
            "version": f"{zlib.crc32(content):08x}-{len(content)}",
            "modified_time": email_file.get("modified_time", ""),
            "size": len(content),
            "web_url": email_file["web_url"],  # the link opens the email (or the zip it is in)
            "path": f"{email_file.get('path', '')}{email_file['name']}/",
            "archive": email_file["name"],
        }
        if len(content) > settings.max_file_bytes:
            out.append({**doc, "error": "This attachment is too large to read."})
            continue
        out.extend(_expand(doc, content, settings, depth))
    return out
