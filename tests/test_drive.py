"""Drive tests using a fake `service` object — no network, no Google libs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lumos.drive import DriveClient, DriveError


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
        self.get_response = {"id": "x", "name": "x"}

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


def test_upload_passes_metadata(drive, fake_service, tmp_path, monkeypatch):
    src = tmp_path / "x.txt"
    src.write_text("hello")

    # Stub MediaFileUpload to avoid pulling in googleapiclient.
    fake_media = object()

    class _FakeMediaFileUpload:
        def __init__(self, *a, **kw):
            pass

    import sys
    import types

    pkg = types.ModuleType("googleapiclient")
    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaFileUpload = _FakeMediaFileUpload
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)

    fake_service._files.create_response = {"id": "abc", "name": "x.txt"}
    meta = drive.upload(src, folder_id="folder-1", name="x.txt", mime_type="text/plain")
    assert meta == {"id": "abc", "name": "x.txt"}
    body = fake_service._files.create_calls[0]["body"]
    assert body == {"name": "x.txt", "parents": ["folder-1"]}


def test_download_writes_file(drive, fake_service, tmp_path, monkeypatch):
    payload = b"hello world"

    class _FakeDownloader:
        def __init__(self, buf, request):
            self.buf = buf
            self._done = False

        def next_chunk(self):
            self.buf.write(payload)
            self._done = True
            return None, True

    import sys
    import types

    pkg = types.ModuleType("googleapiclient")
    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaIoBaseDownload = _FakeDownloader
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)

    # files().get_media is used by download
    fake_service._files.get_media = lambda fileId: _FakeRequestPlaceholder()
    out = tmp_path / "subdir" / "file.bin"
    path = drive.download("xyz", out)
    assert path == out
    assert out.read_bytes() == payload


class _FakeRequestPlaceholder:
    pass


def test_download_rejects_empty_id(drive):
    with pytest.raises(ValueError):
        drive.download("", "/tmp/x")


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
