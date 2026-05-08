"""Google Drive integration.

The Google API client libraries are an optional dependency
(`pip install lumos[gdrive]`). All imports happen inside
:meth:`DriveClient._service` so the rest of Lumos works without them.

Authentication
--------------
Place an OAuth client secret at ``<config.home>/credentials.json``.
On first use, ``DriveClient.authenticate()`` runs a local-server OAuth
flow and caches the resulting refresh token at ``token.json``.

Tests in this repo do not hit the network; they exercise the helpers by
injecting a fake ``service`` object (see ``tests/test_drive.py``).
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import Config

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveError(RuntimeError):
    """Raised for any Drive-related failure (auth, IO, API)."""


class DriveClient:
    """High-level Google Drive helper.

    Methods accept and return plain dicts/strings to keep the surface
    small and easy to mock. ``service`` may be injected directly (used
    by tests); otherwise it is built lazily via the OAuth flow.
    """

    def __init__(self, config: Config, *, service: Any | None = None) -> None:
        self.config = config
        self._service = service

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def authenticate(self, *, headless: bool = False) -> None:
        """Run the OAuth flow if needed and cache credentials.

        ``headless=True`` uses the console flow instead of opening a
        browser — useful on remote machines.
        """
        self._service = self._build_service(force=True, headless=headless)

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self, *, force: bool = False, headless: bool = False) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as e:  # pragma: no cover - exercised by users without extras
            raise DriveError(
                "Google API libraries are not installed. "
                "Install them with: pip install 'lumos[gdrive]'"
            ) from e

        creds: Optional[Credentials] = None
        token_path = self.config.token_path
        if token_path.exists() and not force:
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except Exception as e:
                log.warning("Could not load cached token (%s); re-authenticating.", e)
                creds = None

        if creds and creds.valid:
            pass
        elif creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log.warning("Token refresh failed (%s); re-authenticating.", e)
                creds = None

        if not creds or not creds.valid:
            if not self.config.credentials_path.exists():
                raise DriveError(
                    f"OAuth client secret not found at {self.config.credentials_path}. "
                    "Download it from Google Cloud Console "
                    "(OAuth 2.0 Client ID, type 'Desktop app') and place it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.config.credentials_path), SCOPES
            )
            if headless:
                creds = flow.run_console()
            else:
                creds = flow.run_local_server(port=0)

            self.config.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.token_path.write_text(creds.to_json())

        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #

    DEFAULT_FIELDS = "id, name, mimeType, modifiedTime, size, parents"

    def list_files(
        self,
        *,
        query: Optional[str] = None,
        page_size: int = 50,
        max_results: Optional[int] = None,
        fields: Optional[str] = None,
    ) -> list[dict]:
        """List files matching a Drive query string.

        See https://developers.google.com/drive/api/guides/search-files
        for query syntax. Pages are followed up to ``max_results``.
        """
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")

        field_spec = f"nextPageToken, files({fields or self.DEFAULT_FIELDS})"
        results: list[dict] = []
        page_token: Optional[str] = None
        while True:
            try:
                resp = (
                    self.service.files()
                    .list(
                        q=query,
                        pageSize=page_size,
                        fields=field_spec,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except Exception as e:
                raise DriveError(f"Drive list failed: {e}") from e

            results.extend(resp.get("files", []))
            if max_results is not None and len(results) >= max_results:
                return results[:max_results]
            page_token = resp.get("nextPageToken")
            if not page_token:
                return results

    def search(self, name_contains: str, *, max_results: int = 25) -> list[dict]:
        """Convenience: search by name substring (escaped)."""
        if not name_contains:
            raise ValueError("name_contains must not be empty")
        escaped = name_contains.replace("\\", "\\\\").replace("'", "\\'")
        q = f"name contains '{escaped}' and trashed = false"
        return self.list_files(query=q, max_results=max_results)

    def upload(
        self,
        path: str | os.PathLike[str],
        *,
        folder_id: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> dict:
        """Upload a local file. Returns Drive's file metadata."""
        src = Path(path)
        if not src.is_file():
            raise DriveError(f"upload source is not a file: {src}")

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as e:  # pragma: no cover
            raise DriveError(
                "Google API libraries are not installed. "
                "Install them with: pip install 'lumos[gdrive]'"
            ) from e

        body: dict = {"name": name or src.name}
        if folder_id:
            body["parents"] = [folder_id]

        media = MediaFileUpload(str(src), mimetype=mime_type, resumable=True)
        try:
            return (
                self.service.files()
                .create(body=body, media_body=media, fields=self.DEFAULT_FIELDS)
                .execute()
            )
        except Exception as e:
            raise DriveError(f"Drive upload failed: {e}") from e

    def download(self, file_id: str, dest: str | os.PathLike[str]) -> Path:
        """Download a file by id to ``dest``. Returns the destination path."""
        if not file_id:
            raise ValueError("file_id must not be empty")

        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as e:  # pragma: no cover
            raise DriveError(
                "Google API libraries are not installed. "
                "Install them with: pip install 'lumos[gdrive]'"
            ) from e

        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            request = self.service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
            out.write_bytes(buf.getvalue())
        except Exception as e:
            raise DriveError(f"Drive download failed: {e}") from e
        return out

    def delete(self, file_id: str) -> None:
        if not file_id:
            raise ValueError("file_id must not be empty")
        try:
            self.service.files().delete(fileId=file_id).execute()
        except Exception as e:
            raise DriveError(f"Drive delete failed: {e}") from e

    def create_folder(self, name: str, *, parent_id: Optional[str] = None) -> dict:
        if not name or not name.strip():
            raise ValueError("folder name must not be empty")
        body = {
            "name": name.strip(),
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            body["parents"] = [parent_id]
        try:
            return (
                self.service.files()
                .create(body=body, fields=self.DEFAULT_FIELDS)
                .execute()
            )
        except Exception as e:
            raise DriveError(f"Drive create_folder failed: {e}") from e

    def get(self, file_id: str, *, fields: Optional[str] = None) -> dict:
        try:
            return (
                self.service.files()
                .get(fileId=file_id, fields=fields or self.DEFAULT_FIELDS)
                .execute()
            )
        except Exception as e:
            raise DriveError(f"Drive get failed: {e}") from e

    def iter_all(self, **kwargs) -> Iterable[dict]:
        """Iterator variant of :meth:`list_files` (no max_results cap)."""
        kwargs.pop("max_results", None)
        yield from self.list_files(**kwargs)
