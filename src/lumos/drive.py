"""Google Drive integration — hardened for production single-user use.

Design notes
------------
- **Scope**: we request ``drive.file``, *not* the broad ``drive`` scope, so
  Lumos only ever sees files it created or that the user explicitly
  shared with it via a picker. This is the scope Google recommends in
  2026 and avoids the heavy verification process required for sensitive
  scopes. (See
  https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

- **Token storage**: the cached refresh token is written atomically
  (temp file → fsync → rename) with ``0600`` permissions, so a crash
  mid-write cannot leave a half-token on disk and other local users
  cannot read it.

- **Retries**: every Drive call funnels through :func:`_with_retry`,
  which retries 429 and 5xx with truncated exponential backoff + jitter
  (Google's recommended pattern). Hard errors (auth, 4xx other than 429)
  fail fast.

- **Downloads** are streamed directly to disk in 4 MiB chunks, never
  buffered fully in memory; Google Workspace native files (Docs, Sheets,
  Slides) are exported via ``files.export_media`` to a sensible default
  MIME type, since :py:meth:`get_media` does not work on those.

- **Optional dependency**: ``google-api-python-client`` & friends are
  only imported inside :meth:`_build_service` and the methods that need
  them. Lumos itself works without ``pip install 'lumos[gdrive]'``.

Tests in this repo do not hit the network; they exercise the helpers by
injecting a fake ``service`` object (see ``tests/test_drive.py``).
"""
from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, TypeVar

from .config import Config

log = logging.getLogger(__name__)

# Narrowest scope that still lets us upload and read our own files.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Native Google Workspace MIME types → sensible export targets.
_WORKSPACE_EXPORTS: dict[str, str] = {
    "application/vnd.google-apps.document":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation":
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.google-apps.drawing": "image/png",
    "application/vnd.google-apps.script": "application/vnd.google-apps.script+json",
}

# Default chunk size for streaming downloads. Must be a multiple of 256 KiB
# for chunks other than the last. 4 MiB is a common sweet spot.
DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024

# Anything at or above this size uses a resumable upload; below it, a
# single-shot upload avoids the extra round-trip.
RESUMABLE_THRESHOLD = 5 * 1024 * 1024

# Retry tunables — match Google's published guidance.
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_MAX_RETRIES = 5
_MAX_BACKOFF_SECONDS = 32.0


T = TypeVar("T")


class DriveError(RuntimeError):
    """Raised for any Drive-related failure (auth, IO, API)."""


# --------------------------------------------------------------------------- #
# Retry helper
# --------------------------------------------------------------------------- #

def _http_status(exc: BaseException) -> Optional[int]:
    """Pull the HTTP status code out of a googleapiclient HttpError, if any.

    The googleapiclient ``HttpError`` exposes ``resp.status``. We can't
    rely on the class being importable (it's an optional dep), so we
    duck-type our way to the status.
    """
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if isinstance(status, int):
        return status
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return None


def _with_retry(
    op: Callable[[], T],
    *,
    label: str,
    max_retries: int = _MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``op`` with truncated exponential backoff on transient errors.

    Retries on:
      * HTTP 408, 429, 500, 502, 503, 504
      * ``ConnectionError`` / ``TimeoutError`` (network blips)

    Everything else propagates immediately (wrapped in :class:`DriveError`
    by the caller).
    """
    attempt = 0
    while True:
        try:
            return op()
        except (ConnectionError, TimeoutError) as e:
            transient = True
            status: Optional[int] = None
            err: BaseException = e
        except Exception as e:  # noqa: BLE001 — duck-typed HttpError
            status = _http_status(e)
            transient = status in _RETRYABLE_STATUSES
            err = e
            if not transient:
                raise

        attempt += 1
        if attempt > max_retries:
            log.warning("%s: giving up after %d retries (last: %s)", label, attempt - 1, err)
            raise err

        # Truncated exponential backoff with full jitter.
        # See https://cloud.google.com/storage/docs/retry-strategy
        backoff = min(_MAX_BACKOFF_SECONDS, (2 ** (attempt - 1))) + random.random()
        log.info(
            "%s: transient error %s (status=%s), retry %d/%d in %.2fs",
            label, type(err).__name__, status, attempt, max_retries, backoff,
        )
        sleep(backoff)


# --------------------------------------------------------------------------- #
# Token persistence
# --------------------------------------------------------------------------- #

def _atomic_write_secret(path: Path, contents: str) -> None:
    """Write ``contents`` to ``path`` atomically with 0600 permissions.

    Steps: write a sibling temp file with mode 0600, fsync it, then
    ``os.replace`` onto the destination. ``os.replace`` is atomic on
    POSIX and best-effort atomic on modern Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Open with O_CREAT|O_WRONLY|O_TRUNC at 0600 from the very first byte
    # to avoid the brief window where the file would be world-readable.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(contents)
            fp.flush()
            try:
                os.fsync(fp.fileno())
            except OSError:
                # Some filesystems (procfs in CI) reject fsync. The
                # atomic rename below is still safer than a plain write.
                pass
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    os.replace(tmp, path)
    # Belt-and-braces in case the umask widened the perms after open
    # (shouldn't happen because of explicit 0600 above, but cheap).
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

class DriveClient:
    """High-level Google Drive helper.

    Methods accept and return plain dicts/strings to keep the surface
    small and easy to mock. ``service`` may be injected directly (used
    by tests); otherwise it is built lazily via the OAuth flow.
    """

    DEFAULT_FIELDS = "id, name, mimeType, modifiedTime, size, parents"

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

        refreshed = False
        if creds and creds.valid:
            pass
        elif creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
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
            refreshed = True

        if refreshed:
            _atomic_write_secret(self.config.token_path, creds.to_json())

        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------ #
    # Listing / searching
    # ------------------------------------------------------------------ #

    def list_files(
        self,
        *,
        query: Optional[str] = None,
        page_size: int = 50,
        max_results: Optional[int] = None,
        fields: Optional[str] = None,
        include_trashed: bool = False,
    ) -> list[dict]:
        """List files matching a Drive query string.

        Trashed files are excluded by default (override with
        ``include_trashed=True`` or by writing ``trashed`` into ``query``
        yourself). See
        https://developers.google.com/drive/api/guides/search-files
        for query syntax. Pages are followed up to ``max_results``.
        """
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")

        effective_query = query
        if not include_trashed and (query is None or "trashed" not in query):
            effective_query = (
                f"({query}) and trashed = false" if query else "trashed = false"
            )

        field_spec = f"nextPageToken, files({fields or self.DEFAULT_FIELDS})"
        results: list[dict] = []
        page_token: Optional[str] = None
        while True:
            def _call() -> dict:
                return (
                    self.service.files()
                    .list(
                        q=effective_query,
                        pageSize=page_size,
                        fields=field_spec,
                        pageToken=page_token,
                    )
                    .execute()
                )

            try:
                resp = _with_retry(_call, label="drive.list")
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
        return self.list_files(query=q, max_results=max_results, include_trashed=True)

    def iter_all(self, **kwargs) -> Iterable[dict]:
        """Iterator variant of :meth:`list_files` (no max_results cap)."""
        kwargs.pop("max_results", None)
        yield from self.list_files(**kwargs)

    # ------------------------------------------------------------------ #
    # Upload / download
    # ------------------------------------------------------------------ #

    def upload(
        self,
        path: str | os.PathLike[str],
        *,
        folder_id: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> dict:
        """Upload a local file. Returns Drive's file metadata.

        Uses a single-shot upload for files smaller than
        :data:`RESUMABLE_THRESHOLD` (5 MiB), and a resumable upload above
        that. The resumable path is more robust against transient
        network drops on large uploads.
        """
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

        resumable = src.stat().st_size >= RESUMABLE_THRESHOLD
        media = MediaFileUpload(str(src), mimetype=mime_type, resumable=resumable)

        def _call() -> dict:
            return (
                self.service.files()
                .create(body=body, media_body=media, fields=self.DEFAULT_FIELDS)
                .execute()
            )

        try:
            return _with_retry(_call, label="drive.upload")
        except Exception as e:
            raise DriveError(f"Drive upload failed: {e}") from e

    def download(
        self,
        file_id: str,
        dest: str | os.PathLike[str],
        *,
        export_mime_type: Optional[str] = None,
        chunk_size: int = DOWNLOAD_CHUNK_SIZE,
    ) -> Path:
        """Download a file by id to ``dest``.

        Streams to disk in ``chunk_size`` blocks (default 4 MiB) so very
        large files never sit fully in memory. For native Google
        Workspace files (Docs, Sheets, Slides, etc.) ``export_media`` is
        used automatically with a sensible default target MIME, which
        can be overridden via ``export_mime_type``.
        """
        if not file_id:
            raise ValueError("file_id must not be empty")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as e:  # pragma: no cover
            raise DriveError(
                "Google API libraries are not installed. "
                "Install them with: pip install 'lumos[gdrive]'"
            ) from e

        # Figure out whether this is a Workspace native file. ``get`` is
        # cheap and lets us pick the right download method.
        meta = self.get(file_id, fields="id, name, mimeType")
        source_mime = meta.get("mimeType", "")
        is_workspace = source_mime.startswith("application/vnd.google-apps.")

        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")

        def _make_request():
            if is_workspace:
                target = export_mime_type or _WORKSPACE_EXPORTS.get(
                    source_mime, "application/pdf"
                )
                return self.service.files().export_media(
                    fileId=file_id, mimeType=target
                )
            return self.service.files().get_media(fileId=file_id)

        try:
            with open(tmp, "wb") as fp:
                request = _make_request()
                downloader = MediaIoBaseDownload(fp, request, chunksize=chunk_size)
                done = False
                while not done:
                    # The googleapiclient retries internally on some
                    # statuses, but we wrap with our own backoff too so
                    # transient errors *between* chunks are retried.
                    _status, done = _with_retry(
                        downloader.next_chunk, label="drive.download.chunk"
                    )
            os.replace(tmp, out)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise DriveError(f"Drive download failed: {e}") from e
        return out

    # ------------------------------------------------------------------ #
    # Single-file ops
    # ------------------------------------------------------------------ #

    def delete(self, file_id: str) -> None:
        if not file_id:
            raise ValueError("file_id must not be empty")

        def _call() -> None:
            self.service.files().delete(fileId=file_id).execute()

        try:
            _with_retry(_call, label="drive.delete")
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

        def _call() -> dict:
            return (
                self.service.files()
                .create(body=body, fields=self.DEFAULT_FIELDS)
                .execute()
            )

        try:
            return _with_retry(_call, label="drive.create_folder")
        except Exception as e:
            raise DriveError(f"Drive create_folder failed: {e}") from e

    def get(self, file_id: str, *, fields: Optional[str] = None) -> dict:
        if not file_id:
            raise ValueError("file_id must not be empty")

        def _call() -> dict:
            return (
                self.service.files()
                .get(fileId=file_id, fields=fields or self.DEFAULT_FIELDS)
                .execute()
            )

        try:
            return _with_retry(_call, label="drive.get")
        except Exception as e:
            raise DriveError(f"Drive get failed: {e}") from e
