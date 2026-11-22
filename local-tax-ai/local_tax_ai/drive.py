"""Read-only access to a Local client's Google Drive folder (AFIT, Local Tax workflow).

The client (or the accountant) shares the folder with TASKO's Google service account - the same account the
pre-check uses - as a Viewer; TASKO then lists the folder and downloads its documents to read them. Nothing is
written to Drive. Sign-in is with the service account's key from the environment (LOCAL_TAX_AI_GOOGLE_SERVICE_
ACCOUNT_JSON / _FILE, or the pre-check's PRECHECK_GOOGLE_SERVICE_ACCOUNT_JSON / _FILE), never from a prompt.

`LocalDrive` treats a directory as a folder, for tests and the demo mode.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path

from .config import Settings, get_settings

READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"
# Google-native files, exported to a format the reader understands.
EXPORTS = {
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


class DriveError(Exception):
    """A plain-language problem reaching the folder (not shared, not found, no key)."""


def _file(f: dict, path: str = "") -> dict:
    return {"id": f["id"], "name": f["name"], "mime_type": f.get("mimeType", ""), "version": f.get("md5Checksum") or f.get("modifiedTime", ""),
            "modified_time": f.get("modifiedTime", ""), "size": int(f.get("size", 0) or 0),
            "web_url": f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"), "path": path}


class GoogleDrive:
    def __init__(self, settings: Settings):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        raw = settings.google_service_account_json or os.environ.get("PRECHECK_GOOGLE_SERVICE_ACCOUNT_JSON", "")
        path = settings.google_service_account_file or os.environ.get("PRECHECK_GOOGLE_SERVICE_ACCOUNT_FILE", "")
        if raw:
            creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=[READONLY_SCOPE])
        elif path:
            creds = service_account.Credentials.from_service_account_file(path, scopes=[READONLY_SCOPE])
        else:
            raise DriveError("TASKO has no Google service account key configured, so it can't read Drive folders yet.")
        self.account_email = creds.service_account_email
        import google_auth_httplib2
        import httplib2

        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=settings.drive_timeout_s))
        self._svc = build("drive", "v3", http=http, cache_discovery=False)
        self._max_files, self._max_bytes = settings.max_files_per_folder, settings.max_file_bytes

    def _denied(self, exc) -> DriveError:
        if exc.resp.status in (403, 404):
            return DriveError(f"TASKO can't open this Drive folder yet. Share it (Viewer) with {self.account_email}.")
        return DriveError(f"Google Drive returned an error ({exc.resp.status}).")

    def list_folder(self, folder_id: str) -> tuple[list[dict], bool]:
        from googleapiclient.errors import HttpError

        files, queue = [], [(folder_id, "")]
        try:
            while queue and len(files) <= self._max_files:
                parent, path = queue.pop(0)
                token = None
                while True:
                    resp = self._svc.files().list(
                        q=f"'{parent}' in parents and trashed = false", pageSize=200, pageToken=token, supportsAllDrives=True,
                        includeItemsFromAllDrives=True, fields="nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, size, webViewLink)",
                    ).execute()
                    for f in resp.get("files", []):
                        if f["mimeType"] == FOLDER_MIME:
                            queue.append((f["id"], f"{path}{f['name']}/"))
                        else:
                            files.append(_file(f, path))
                    token = resp.get("nextPageToken")
                    if not token:
                        break
        except HttpError as exc:
            raise self._denied(exc) from exc
        return files[: self._max_files], bool(queue) or len(files) > self._max_files

    def download(self, file_id: str) -> tuple[bytes, str, str]:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaIoBaseDownload

        try:
            f = self._svc.files().get(fileId=file_id, supportsAllDrives=True, fields="id, name, mimeType, size").execute()
            name, mime = f["name"], f["mimeType"]
            if mime in EXPORTS:
                mime, ext = EXPORTS[mime]
                request = self._svc.files().export_media(fileId=file_id, mimeType=mime)
                name += ext
            elif mime.startswith("application/vnd.google-apps."):
                raise DriveError(f"{name} is a Google {mime.rsplit('.', 1)[-1]}: it can't be read.")
            else:
                if int(f.get("size", 0) or 0) > self._max_bytes:
                    raise DriveError(f"{name} is too large to read.")
                request = self._svc.files().get_media(fileId=file_id, supportsAllDrives=True)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request, chunksize=4 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        except HttpError as exc:
            raise self._denied(exc) from exc
        return buffer.getvalue(), name, mime


class LocalDrive:
    """A directory under `local_drive_root` stands in for a Drive folder (folder id = its name)."""

    account_email = "tasko-local@demo"

    def __init__(self, settings: Settings):
        self.root = Path(settings.local_drive_root)
        self._max_files = settings.max_files_per_folder

    def _folder(self, folder_id: str) -> Path:
        folder = (self.root / folder_id).resolve()
        if self.root.resolve() not in folder.parents or not folder.is_dir():
            raise DriveError(f"TASKO can't open this Drive folder yet. Share it (Viewer) with {self.account_email}.")
        return folder

    def list_folder(self, folder_id: str) -> tuple[list[dict], bool]:
        folder = self._folder(folder_id)
        files = []
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.name.startswith((".", "~$")):
                rel = path.relative_to(folder).as_posix()
                files.append({"id": f"{folder_id}:{rel}", "name": path.name, "mime_type": "", "version": hashlib.md5(path.read_bytes()).hexdigest(),
                              "modified_time": str(int(path.stat().st_mtime)), "size": path.stat().st_size, "web_url": f"local://{folder_id}/{rel}",
                              "path": rel[: -len(path.name)]})
        return files[: self._max_files], len(files) > self._max_files

    def download(self, file_id: str) -> tuple[bytes, str, str]:
        folder_id, rel = file_id.split(":", 1) if ":" in file_id else ("", file_id)
        path = (self._folder(folder_id) / rel).resolve()
        if self._folder(folder_id) not in path.parents or not path.is_file():
            raise DriveError("This file is not in the folder.")
        return path.read_bytes(), path.name, ""


def get_drive(settings: Settings | None = None):
    settings = settings or get_settings()
    return LocalDrive(settings) if settings.drive_mode == "local" else GoogleDrive(settings)


def listing(folder_id: str) -> dict:
    drive = get_drive()
    files, truncated = drive.list_folder(folder_id)
    return {"account_email": drive.account_email, "files": files, "truncated": truncated}


def fetch(file_id: str) -> dict:
    data, name, mime = get_drive().download(file_id)
    return {"name": name, "mime_type": mime, "content_b64": base64.b64encode(data).decode(), "size": len(data)}


def account() -> dict:
    try:
        return {"account_email": get_drive().account_email, "configured": True}
    except DriveError as exc:
        return {"account_email": "", "configured": False, "detail": str(exc)}
