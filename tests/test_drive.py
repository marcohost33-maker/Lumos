"""Drive tests using a fake `service` object — no network, no Google libs."""
from __future__ import annotations

import os
import stat
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lumos.drive import (
    DOWNLOAD_CHUNK_SIZE,
    RESUMABLE_THRESHOLD,
    SCOPES,
    DriveClient,
    DriveError,
    _atomic_write_secret,
    _http_status,
    _with_retry,
)


# --------------------------------------------------------------------------- #
# Fake Drive service
# --------------------------------------------------------------------------- #

class _FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeFiles:
    def __init__(self):
        self.list_calls: list[dict] = []
        self.list_responses: list[dict] = [{"files": [], "nextPageToken": None}]
        self.create_calls: list[dict] = []
        self.create_response = {"id": "new-id", "name": "new"}
        self.delete_calls: list[str] = []
        self.get_calls: list[dict] = []
        self.get_response: dict = {
            "id": "x", "name": "x", "mimeType": "application/octet-stream",
        }
        self.get_media_calls: list[str] = []
        self.export_media_calls: list[dict] = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        idx = min(len(self.list_calls) - 1, len(self.list_responses) - 1)
        return _FakeRequest(self.list_responses[idx])

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return _FakeRequest(self.create_response)

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs["fileId"])
        return _FakeRequest(None)

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _FakeRequest(self.get_response)

    def get_media(self, fileId):
        self.get_media_calls.append(fileId)
        return object()

    def export_media(self, fileId, mimeType):
        self.export_media_calls.append({"fileId": fileId, "mimeType": mimeType})
        return object()


class _FakeService:
    def __init__(self):
        self._files = _FakeFiles()

    def files(self):
        return self._files


@pytest.fixture
def fake_service():
    return _FakeService()


@pytest.fixture
def drive(config, fake_service) -> DriveClient:
    return DriveClient(config, service=fake_service)


# --------------------------------------------------------------------------- #
# list_files / search / paging
# --------------------------------------------------------------------------- #

def test_list_files_returns_results(drive, fake_service):
    fake_service._files.list_responses = [
        {"files": [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]}
    ]
    files = drive.list_files()
    assert [f["id"] for f in files] == ["1", "2"]
    call = fake_service._files.list_calls[0]
    assert call["pageSize"] == 50
    assert "nextPageToken" in call["fields"]
    # Default excludes trashed.
    assert call["q"] == "trashed = false"


def test_list_files_default_query_with_user_query(drive, fake_service):
    fake_service._files.list_responses = [{"files": []}]
    drive.list_files(query="name = 'foo'")
    q = fake_service._files.list_calls[0]["q"]
    assert "trashed = false" in q
    assert "name = 'foo'" in q


def test_list_files_respects_user_query_with_trashed(drive, fake_service):
    """If user already mentions trashed, don't auto-append."""
    fake_service._files.list_responses = [{"files": []}]
    drive.list_files(query="trashed = true")
    assert fake_service._files.list_calls[0]["q"] == "trashed = true"


def test_list_files_include_trashed_flag(drive, fake_service):
    fake_service._files.list_responses = [{"files": []}]
    drive.list_files(include_trashed=True)
    assert fake_service._files.list_calls[0]["q"] is None


def test_list_files_paginates(drive, fake_service):
    fake_service._files.list_responses = [
        {"files": [{"id": "1"}], "nextPageToken": "tok"},
        {"files": [{"id": "2"}]},
    ]
    files = drive.list_files()
    assert [f["id"] for f in files] == ["1", "2"]
    assert fake_service._files.list_calls[1]["pageToken"] == "tok"


def test_list_files_respects_max_results(drive, fake_service):
    fake_service._files.list_responses = [
        {"files": [{"id": str(i)} for i in range(50)], "nextPageToken": "tok"},
    ]
    files = drive.list_files(max_results=10)
    assert len(files) == 10


def test_list_files_validates_page_size(drive):
    with pytest.raises(ValueError):
        drive.list_files(page_size=0)
    with pytest.raises(ValueError):
        drive.list_files(page_size=10_000)


def test_list_files_wraps_errors(drive, fake_service):
    fake_service._files.list = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(DriveError):
        drive.list_files()


def test_search_escapes_quotes(drive, fake_service):
    fake_service._files.list_responses = [{"files": []}]
    drive.search("o'reilly")
    q = fake_service._files.list_calls[0]["q"]
    assert "o\\'reilly" in q
    assert "trashed = false" in q


def test_search_rejects_empty(drive):
    with pytest.raises(ValueError):
        drive.search("")


# --------------------------------------------------------------------------- #
# upload / download / delete / create_folder / get
# --------------------------------------------------------------------------- #

def test_upload_missing_file(drive, tmp_path):
    with pytest.raises(DriveError):
        drive.upload(tmp_path / "does-not-exist.txt")


def _install_fake_media_upload(monkeypatch) -> list[dict]:
    """Install a fake MediaFileUpload; returns a list of constructor kwargs."""
    captured: list[dict] = []

    class _FakeMediaFileUpload:
        def __init__(self, path, mimetype=None, resumable=False, **kw):
            captured.append({"path": path, "mimetype": mimetype, "resumable": resumable})

    pkg = types.ModuleType("googleapiclient")
    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaFileUpload = _FakeMediaFileUpload
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)
    return captured


def test_upload_passes_metadata(drive, fake_service, tmp_path, monkeypatch):
    src = tmp_path / "x.txt"
    src.write_text("hello")

    captured = _install_fake_media_upload(monkeypatch)
    fake_service._files.create_response = {"id": "abc", "name": "x.txt"}
    meta = drive.upload(src, folder_id="folder-1", name="x.txt", mime_type="text/plain")
    assert meta == {"id": "abc", "name": "x.txt"}
    body = fake_service._files.create_calls[0]["body"]
    assert body == {"name": "x.txt", "parents": ["folder-1"]}
    # Small file → single-shot upload.
    assert captured[0]["resumable"] is False
    assert captured[0]["mimetype"] == "text/plain"


def test_upload_large_file_uses_resumable(drive, fake_service, tmp_path, monkeypatch):
    src = tmp_path / "big.bin"
    src.write_bytes(b"\0" * (RESUMABLE_THRESHOLD + 1))
    captured = _install_fake_media_upload(monkeypatch)
    fake_service._files.create_response = {"id": "abc"}
    drive.upload(src)
    assert captured[0]["resumable"] is True


def _install_fake_downloader(monkeypatch, payload: bytes, *, chunks: int = 1):
    """Install a fake MediaIoBaseDownload that writes `payload` in N chunks."""
    class _FakeDownloader:
        def __init__(self, fp, request, chunksize=None):
            self.fp = fp
            self.request = request
            self.chunksize = chunksize
            self._remaining = list(_split(payload, chunks))

        def next_chunk(self):
            piece = self._remaining.pop(0)
            self.fp.write(piece)
            return None, not self._remaining

    pkg = types.ModuleType("googleapiclient")
    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaIoBaseDownload = _FakeDownloader
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)
    return _FakeDownloader


def _split(data: bytes, n: int) -> list[bytes]:
    if n <= 1:
        return [data]
    step = max(1, len(data) // n)
    return [data[i : i + step] for i in range(0, len(data), step)] or [b""]


def test_download_writes_file_streaming(drive, fake_service, tmp_path, monkeypatch):
    payload = b"hello world! " * 1000
    _install_fake_downloader(monkeypatch, payload, chunks=3)
    fake_service._files.get_response = {
        "id": "xyz", "name": "x", "mimeType": "application/octet-stream",
    }
    out = tmp_path / "subdir" / "file.bin"
    path = drive.download("xyz", out, chunk_size=512)
    assert path == out
    assert out.read_bytes() == payload
    # Streamed via get_media (not export_media).
    assert fake_service._files.get_media_calls == ["xyz"]
    assert fake_service._files.export_media_calls == []
    # No leftover .part file.
    assert not (out.with_suffix(out.suffix + ".part")).exists()


def test_download_uses_export_for_workspace_files(
    drive, fake_service, tmp_path, monkeypatch
):
    _install_fake_downloader(monkeypatch, b"DOCXBYTES")
    fake_service._files.get_response = {
        "id": "doc1", "name": "Notes", "mimeType": "application/vnd.google-apps.document",
    }
    out = tmp_path / "Notes.docx"
    drive.download("doc1", out)
    # Must have used export_media, not get_media.
    assert fake_service._files.get_media_calls == []
    assert len(fake_service._files.export_media_calls) == 1
    call = fake_service._files.export_media_calls[0]
    assert call["fileId"] == "doc1"
    # Default export for Docs is .docx (Office wordprocessing MIME).
    assert call["mimeType"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_download_export_mime_type_override(drive, fake_service, tmp_path, monkeypatch):
    _install_fake_downloader(monkeypatch, b"%PDF-1.7")
    fake_service._files.get_response = {
        "id": "doc1", "name": "Notes", "mimeType": "application/vnd.google-apps.document",
    }
    out = tmp_path / "Notes.pdf"
    drive.download("doc1", out, export_mime_type="application/pdf")
    assert fake_service._files.export_media_calls[0]["mimeType"] == "application/pdf"


def test_download_cleans_up_partial_file_on_error(
    drive, fake_service, tmp_path, monkeypatch
):
    class _Boom:
        def __init__(self, fp, request, chunksize=None):
            self.fp = fp

        def next_chunk(self):
            self.fp.write(b"partial")
            raise RuntimeError("boom")

    pkg = types.ModuleType("googleapiclient")
    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaIoBaseDownload = _Boom
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)
    fake_service._files.get_response = {
        "id": "xyz", "name": "x", "mimeType": "application/octet-stream",
    }
    out = tmp_path / "x.bin"
    with pytest.raises(DriveError):
        drive.download("xyz", out)
    assert not out.exists()
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_download_rejects_empty_id(drive):
    with pytest.raises(ValueError):
        drive.download("", "/tmp/x")


def test_download_rejects_bad_chunk_size(drive, fake_service):
    fake_service._files.get_response = {"id": "x", "mimeType": "application/octet-stream"}
    with pytest.raises(ValueError):
        drive.download("x", "/tmp/out", chunk_size=0)


def test_delete_calls_api(drive, fake_service):
    drive.delete("abc")
    assert fake_service._files.delete_calls == ["abc"]


def test_delete_rejects_empty_id(drive):
    with pytest.raises(ValueError):
        drive.delete("")


def test_delete_wraps_errors(drive, fake_service):
    fake_service._files.delete = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(DriveError):
        drive.delete("abc")


def test_create_folder_passes_mime_and_parent(drive, fake_service):
    fake_service._files.create_response = {"id": "f1", "name": "Notes"}
    meta = drive.create_folder("Notes", parent_id="root")
    assert meta == {"id": "f1", "name": "Notes"}
    body = fake_service._files.create_calls[0]["body"]
    assert body["mimeType"] == "application/vnd.google-apps.folder"
    assert body["parents"] == ["root"]


def test_create_folder_rejects_empty(drive):
    with pytest.raises(ValueError):
        drive.create_folder("   ")


def test_get_calls_api(drive, fake_service):
    fake_service._files.get_response = {"id": "g1", "name": "x"}
    meta = drive.get("g1")
    assert meta == {"id": "g1", "name": "x"}
    assert fake_service._files.get_calls[0]["fileId"] == "g1"


# --------------------------------------------------------------------------- #
# Auth error path (no google libs needed for this assertion)
# --------------------------------------------------------------------------- #

def test_authenticate_without_credentials_raises(config, monkeypatch):
    """Without credentials.json we should get a clear DriveError."""
    # Ensure no service injected, force the build path to run.
    client = DriveClient(config)

    # Stub google libs so import succeeds inside _build_service.
    import sys
    import types

    google = types.ModuleType("google")
    google_auth = types.ModuleType("google.auth")
    google_auth_transport = types.ModuleType("google.auth.transport")
    google_auth_transport_requests = types.ModuleType("google.auth.transport.requests")
    google_auth_transport_requests.Request = object
    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2_credentials = types.ModuleType("google.oauth2.credentials")
    google_oauth2_credentials.Credentials = object
    google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
    google_auth_oauthlib_flow = types.ModuleType("google_auth_oauthlib.flow")

    class _FlowStub:
        @classmethod
        def from_client_secrets_file(cls, *a, **kw):  # pragma: no cover
            raise AssertionError("should not reach here")

    google_auth_oauthlib_flow.InstalledAppFlow = _FlowStub
    googleapiclient = types.ModuleType("googleapiclient")
    googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
    googleapiclient_discovery.build = lambda *a, **kw: object()

    for name, mod in {
        "google": google,
        "google.auth": google_auth,
        "google.auth.transport": google_auth_transport,
        "google.auth.transport.requests": google_auth_transport_requests,
        "google.oauth2": google_oauth2,
        "google.oauth2.credentials": google_oauth2_credentials,
        "google_auth_oauthlib": google_auth_oauthlib,
        "google_auth_oauthlib.flow": google_auth_oauthlib_flow,
        "googleapiclient": googleapiclient,
        "googleapiclient.discovery": googleapiclient_discovery,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    config.ensure_dirs()
    # No credentials.json on disk → DriveError.
    with pytest.raises(DriveError):
        client.authenticate()


def test_drive_error_when_libs_missing(config, monkeypatch):
    """With google libs missing, we get a friendly DriveError."""
    client = DriveClient(config)
    import builtins

    real_import = builtins.__import__

    def _fail(name, *a, **kw):
        if name.startswith("google") or name == "googleapiclient":
            raise ImportError(name)
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _fail)
    with pytest.raises(DriveError):
        client._build_service()


# --------------------------------------------------------------------------- #
# Scope, retry, and atomic-write hardening
# --------------------------------------------------------------------------- #

def test_scope_is_drive_file_least_privilege():
    """Lumos requests drive.file (per-app files only), not the broad drive scope."""
    assert SCOPES == ["https://www.googleapis.com/auth/drive.file"]


class _FakeHttpError(Exception):
    """Duck-typed googleapiclient HttpError with a .resp.status attribute."""

    def __init__(self, status: int, message: str = "err") -> None:
        super().__init__(message)
        self.resp = types.SimpleNamespace(status=status)


def test_http_status_extracts_int_status():
    assert _http_status(_FakeHttpError(503)) == 503


def test_http_status_extracts_str_status():
    err = Exception()
    err.resp = types.SimpleNamespace(status="429")  # type: ignore[attr-defined]
    assert _http_status(err) == 429


def test_http_status_none_for_other_exception():
    assert _http_status(ValueError("x")) is None


def test_with_retry_retries_transient_then_succeeds():
    calls = {"n": 0}
    sleeps: list[float] = []

    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeHttpError(503)
        return "ok"

    result = _with_retry(op, label="test", sleep=sleeps.append)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2
    # First backoff is in [1.0, 2.0), second in [2.0, 3.0).
    assert 1.0 <= sleeps[0] < 2.0
    assert 2.0 <= sleeps[1] < 3.0


def test_with_retry_does_not_retry_non_transient():
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise _FakeHttpError(403)  # auth error → fail fast

    with pytest.raises(_FakeHttpError):
        _with_retry(op, label="test", sleep=lambda _: None)
    assert calls["n"] == 1


def test_with_retry_retries_connection_error():
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("boom")
        return "ok"

    assert _with_retry(op, label="test", sleep=lambda _: None) == "ok"
    assert calls["n"] == 2


def test_with_retry_gives_up_after_max_retries():
    def op():
        raise _FakeHttpError(503)

    with pytest.raises(_FakeHttpError):
        _with_retry(op, label="test", max_retries=2, sleep=lambda _: None)


def test_list_files_retries_on_transient_error(drive, fake_service, monkeypatch):
    """A 503 followed by success should be silently retried."""
    monkeypatch.setattr("lumos.drive.time.sleep", lambda _: None)

    state = {"n": 0}
    real_list = fake_service._files.list

    def flaky_list(**kw):
        state["n"] += 1
        if state["n"] == 1:
            class _Req:
                def execute(self_):
                    raise _FakeHttpError(503)

            return _Req()
        return real_list(**kw)

    fake_service._files.list_responses = [{"files": [{"id": "1"}]}]
    fake_service._files.list = flaky_list
    files = drive.list_files()
    assert [f["id"] for f in files] == ["1"]
    assert state["n"] == 2  # transient call + retry


# --------------------------------------------------------------------------- #
# Token file: atomic write + 0600 perms
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perms only")
def test_atomic_write_secret_sets_0600(tmp_path):
    target = tmp_path / "secrets" / "token.json"
    _atomic_write_secret(target, '{"refresh_token": "abc"}')
    assert target.read_text() == '{"refresh_token": "abc"}'
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_atomic_write_secret_overwrites_existing(tmp_path):
    target = tmp_path / "token.json"
    target.write_text("old")
    _atomic_write_secret(target, "new")
    assert target.read_text() == "new"
    # Temp sibling must be cleaned up.
    assert not target.with_suffix(target.suffix + ".tmp").exists()


def test_atomic_write_secret_leaves_no_tmp_on_failure(tmp_path, monkeypatch):
    """If fdopen/write fails mid-flight, the temp file is unlinked."""
    target = tmp_path / "token.json"

    real_fdopen = os.fdopen
    calls = {"n": 0}

    def boom_fdopen(fd, *a, **kw):
        calls["n"] += 1
        # Close the fd so we don't leak it, then raise.
        os.close(fd)
        raise OSError("disk on fire")

    monkeypatch.setattr(os, "fdopen", boom_fdopen)
    with pytest.raises(OSError):
        _atomic_write_secret(target, "x")
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".tmp").exists()


# --------------------------------------------------------------------------- #
# Misc constants sanity-check
# --------------------------------------------------------------------------- #

def test_download_chunk_size_is_multiple_of_256kib():
    assert DOWNLOAD_CHUNK_SIZE % (256 * 1024) == 0
    assert DOWNLOAD_CHUNK_SIZE >= 256 * 1024


def test_resumable_threshold_is_reasonable():
    assert 1024 * 1024 <= RESUMABLE_THRESHOLD <= 100 * 1024 * 1024
