"""Zip archives in a job folder.

Some job folders hold one zip with the documents inside. The archive is opened in memory and
each file inside becomes its own document, exactly as if it sat in the folder: it is parsed,
classified, indexed and cited on its own ("Trial Balance.xlsx (in Documents.zip)").

A member's id is "<zip file id>!<path inside the zip>" and its version is the CRC and size of
its content, so re-uploading the zip with one file changed re-reads only that file.
"""
import io
import zipfile

from .config import Settings

SEP = "!"
MAX_DEPTH = 2  # a zip inside a zip is opened; deeper nesting is not


def container_of(file_id: str) -> str:
    """The id of the Drive file a document came from (itself, unless it is inside a zip)."""
    return file_id.split(SEP, 1)[0]


def display_name(file: dict) -> str:
    """"Trial Balance.xlsx (in Documents.zip)" for a document inside a zip, else its name."""
    for part in (file.get("path") or "").split("/"):
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
        if base.lower().endswith(".zip"):
            if depth >= MAX_DEPTH:
                out.append({**doc, "error": "A zip inside a zip inside a zip is not opened."})
                continue
            inner, problem = members(content, doc, settings, depth + 1)
            out.extend(inner)
            if problem:
                out.append({**doc, "error": problem})
            continue
        out.append({**doc, "data": content})
    return out, ""
