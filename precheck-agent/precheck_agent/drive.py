"""Read-only access to a job's Google Drive folder.

Sign-in is done here, in code, with a Google service account that has the read-only Drive
scope and has been given access to the job folder. The key comes from the secret manager
(a mounted file or an injected environment value) — never from a skill, a prompt or the
repository. Reading uses only files.list, files.get (one file's metadata, for a file link),
files.get_media and files.export. The one write is `upload_workpaper` (AFIT, 21 Nov 2026): a prepared
workpaper saved to the task's folder, when a person asks for it, with its own write-scoped sign-in.

`LocalDrive` treats a directory as a folder, for tests and the demo mode.
"""
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Settings, get_settings
from .parsing import GOOGLE_EXPORTS

READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    # What "changed" means: md5Checksum for uploaded files; modifiedTime for Google-native
    # files (Docs, Sheets), which have no checksum.
    version: str
    modified_time: str
    size: int
    web_url: str
    path: str = ""  # sub-folder path inside the job folder, for display

    def as_dict(self) -> dict:
        return asdict(self)


def is_zip(name: str, mime_type: str = "") -> bool:
    return name.lower().endswith(".zip") or mime_type in ("application/zip", "application/x-zip-compressed")


class DriveError(Exception):
    """A plain-language problem reaching the folder (not shared, not found, no key)."""


class GoogleDrive:
    def __init__(self, settings: Settings):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if settings.google_service_account_json:
            info = json.loads(settings.google_service_account_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=[READONLY_SCOPE])
        elif settings.google_service_account_file:
            creds = service_account.Credentials.from_service_account_file(
                settings.google_service_account_file, scopes=[READONLY_SCOPE]
            )
        else:
            raise DriveError("The pre-check service has no Google service account key configured.")
        self.account_email = creds.service_account_email
        import google_auth_httplib2
        import httplib2

        # A timeout on every Drive request: without one, a stalled download hangs the run forever.
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=settings.drive_timeout_s))
        self._svc = build("drive", "v3", http=http, cache_discovery=False)
        self._max_files = settings.max_files_per_folder
        self._max_bytes = settings.max_file_bytes
        self._max_zip_bytes = settings.max_zip_bytes

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        """Metadata only — no file content is downloaded here."""
        from googleapiclient.errors import HttpError

        files: list[DriveFile] = []
        self.truncated = False
        queue = [(folder_id, "")]
        self.folders = {folder_id: ""}  # folder id -> its path inside the task folder
        try:
            while queue and len(files) < self._max_files:
                parent, path = queue.pop(0)
                token = None
                while True:
                    resp = (
                        self._svc.files()
                        .list(
                            q=f"'{parent}' in parents and trashed = false",
                            fields="nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, size, webViewLink)",
                            pageSize=200,
                            pageToken=token,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                        )
                        .execute()
                    )
                    for f in resp.get("files", []):
                        if f["mimeType"] == FOLDER_MIME:
                            queue.append((f["id"], f"{path}{f['name']}/"))
                            self.folders[f["id"]] = f"{path}{f['name']}/"
                            continue
                        files.append(
                            DriveFile(
                                id=f["id"],
                                name=f["name"],
                                mime_type=f["mimeType"],
                                version=f.get("md5Checksum") or f.get("modifiedTime", ""),
                                modified_time=f.get("modifiedTime", ""),
                                size=int(f.get("size", 0) or 0),
                                web_url=f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"),
                                path=path,
                            )
                        )
                    token = resp.get("nextPageToken")
                    if not token:
                        break
        except HttpError as exc:
            if exc.resp.status in (403, 404):
                raise DriveError(
                    f"The pre-check cannot open this Drive folder. Share it (Viewer) with {self.account_email}."
                ) from exc
            raise DriveError(f"Google Drive returned an error ({exc.resp.status}).") from exc
        self.truncated = bool(queue) or len(files) > self._max_files  # folders or files left unread
        return files[: self._max_files]

    def get_file(self, file_id: str) -> DriveFile:
        """One file's metadata (a link to a single file rather than a folder)."""
        from googleapiclient.errors import HttpError

        try:
            f = self._svc.files().get(fileId=file_id, supportsAllDrives=True,
                                      fields="id, name, mimeType, md5Checksum, modifiedTime, size, webViewLink").execute()
        except HttpError as exc:
            if exc.resp.status in (403, 404):
                raise DriveError(f"This Drive file can't be opened. Share it (Viewer) with {self.account_email}.") from exc
            raise DriveError(f"Google Drive returned an error ({exc.resp.status}).") from exc
        return DriveFile(id=f["id"], name=f["name"], mime_type=f["mimeType"], version=f.get("md5Checksum") or f.get("modifiedTime", ""),
                         modified_time=f.get("modifiedTime", ""), size=int(f.get("size", 0) or 0),
                         web_url=f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"))

    def download(self, file: DriveFile) -> tuple[bytes, str, str]:
        """(bytes, file name to parse as, MIME type). Google-native files are exported."""
        from googleapiclient.http import MediaIoBaseDownload

        name, mime = file.name, file.mime_type
        if file.mime_type in GOOGLE_EXPORTS:
            mime, ext = GOOGLE_EXPORTS[file.mime_type]
            request = self._svc.files().export_media(fileId=file.id, mimeType=mime)
            name = file.name + ext
        elif file.mime_type.startswith("application/vnd.google-apps."):
            return b"", name, mime  # forms, drawings, shortcuts: nothing to read
        else:
            if file.size > (self._max_zip_bytes if is_zip(file.name, file.mime_type) else self._max_bytes):
                return b"", name, mime
            request = self._svc.files().get_media(fileId=file.id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request, chunksize=4 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue(), name, mime


class LocalDrive:
    """A directory under `local_drive_root` stands in for a Drive folder (folder id = its name)."""

    def __init__(self, settings: Settings):
        self.root = Path(settings.local_drive_root)
        self._max_files = settings.max_files_per_folder  # the same limit as Drive, so tests see what Drive does
        self.truncated = False

    def _folder(self, folder_id: str) -> Path:
        folder = (self.root / folder_id).resolve()
        if self.root.resolve() not in folder.parents or not folder.is_dir():
            raise DriveError("This folder does not exist in the local fixtures.")
        return folder

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        folder = self._folder(folder_id)
        files = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name.startswith((".", "~$")):
                continue
            rel = path.relative_to(folder).as_posix()
            stat = path.stat()
            files.append(
                DriveFile(
                    id=f"{folder_id}:{rel}",
                    name=path.name,
                    mime_type="",
                    version=hashlib.md5(path.read_bytes()).hexdigest(),
                    modified_time=str(int(stat.st_mtime)),
                    size=stat.st_size,
                    web_url=f"local://{folder_id}/{rel}",
                    path=rel[: -len(path.name)],
                )
            )
        self.truncated = len(files) > self._max_files
        return files[: self._max_files]

    def get_file(self, file_id: str) -> DriveFile:
        """file id: "<folder>:<path inside it>"."""
        folder_id, rel = file_id.split(":", 1) if ":" in file_id else ("", file_id)
        path = self._folder(folder_id) / rel
        if not path.is_file():
            raise DriveError("This file does not exist in the local fixtures.")
        return DriveFile(id=f"{folder_id}:{rel}", name=path.name, mime_type="", version=hashlib.md5(path.read_bytes()).hexdigest(),
                         modified_time=str(int(path.stat().st_mtime)), size=path.stat().st_size, web_url=f"local://{folder_id}/{rel}")

    def download(self, file: DriveFile) -> tuple[bytes, str, str]:
        folder_id, rel = file.id.split(":", 1)
        return (self._folder(folder_id) / rel).read_bytes(), file.name, file.mime_type


def get_drive(settings: Settings | None = None):
    settings = settings or get_settings()
    return LocalDrive(settings) if settings.drive_mode == "local" else GoogleDrive(settings)


def link_to_place(file: dict, block: dict) -> str:
    """A link that opens the file in Drive as close to the cited place as Drive allows:
    a cell range for Google Sheets; the file itself for everything else (Drive's viewer has no
    stable anchors for a paragraph or a PDF line)."""
    url = file.get("web_url", "")
    if file.get("mime_type") == "application/vnd.google-apps.spreadsheet" and block.get("a1"):
        base = url.split("#")[0]
        sheet = block.get("sheet")
        rng = f"'{sheet}'!{block['a1']}" if sheet else block["a1"]
        from urllib.parse import quote

        return f"{base}#range={quote(rng)}"
    return url


# --- saving a workpaper to the task's Drive folder (AFIT, 21 Nov 2026) --------------------------------

WRITE_SCOPE = "https://www.googleapis.com/auth/drive"


def upload_workpaper(folder_id: str, name: str, data: bytes, mime_type: str, settings: Settings | None = None) -> dict:
    """Save a prepared workpaper into a Drive folder: the one call that writes to Drive, made only when a
    person asks for it. A file of the same name in the folder is replaced (a new version, same link).
    Returns {"id", "name", "web_url"}. Needs the service account to be an editor of the folder."""
    s = settings or get_settings()
    if s.drive_mode == "local":
        folder = LocalDrive(s)._folder(folder_id)
        target = folder / "Workpapers" / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        return {"id": f"local:{folder_id}/Workpapers/{name}", "name": name, "web_url": target.resolve().as_uri()}
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseUpload

    if s.google_service_account_json:
        creds = service_account.Credentials.from_service_account_info(json.loads(s.google_service_account_json), scopes=[WRITE_SCOPE])
    elif s.google_service_account_file:
        creds = service_account.Credentials.from_service_account_file(s.google_service_account_file, scopes=[WRITE_SCOPE])
    else:
        raise DriveError("The pre-check service has no Google service account key configured.")
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
    safe = name.replace("'", "\'")
    try:
        same = svc.files().list(q=f"'{folder_id}' in parents and name = '{safe}' and trashed = false", fields="files(id)",
                                supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get("files", [])
        if same:
            f = svc.files().update(fileId=same[0]["id"], media_body=media, fields="id, name, webViewLink", supportsAllDrives=True).execute()
        else:
            f = svc.files().create(body={"name": name, "parents": [folder_id]}, media_body=media, fields="id, name, webViewLink",
                                   supportsAllDrives=True).execute()
    except HttpError as exc:
        status = getattr(exc.resp, "status", 0)
        if status in (403, 404):
            raise DriveError(f"The workpaper could not be saved: share the task's Drive folder with {creds.service_account_email} as an "
                             "Editor (it has view access only), then try again.") from exc
        raise DriveError("Google Drive refused the workpaper. Try again in a moment.") from exc
    return {"id": f["id"], "name": f.get("name", name), "web_url": f.get("webViewLink", "")}
