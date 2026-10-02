"""Read-only access to a job's Google Drive folder.

Sign-in is done here, in code, with a Google service account that has the read-only Drive
scope and has been given access to the job folder. The key comes from the secret manager
(a mounted file or an injected environment value) — never from a skill, a prompt or the
repository. This service never writes to Drive: the only API calls are files.list,
files.get_media and files.export.

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
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._max_files = settings.max_files_per_folder
        self._max_bytes = settings.max_file_bytes
        self._max_zip_bytes = settings.max_zip_bytes

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        """Metadata only — no file content is downloaded here."""
        from googleapiclient.errors import HttpError

        files: list[DriveFile] = []
        queue = [(folder_id, "")]
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
        return files[: self._max_files]

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
        return files

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
