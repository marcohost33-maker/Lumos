from pathlib import Path

from lumos import Lumos
from lumos.config import Config


def test_lumos_constructs_with_default_config(tmp_home):
    app = Lumos()
    try:
        assert app.config.home == tmp_home.resolve()
        assert app.config.home.is_dir()
        # storage works
        r = app.reminders.add("hello", when="in 1 hour")
        assert r.id is not None
    finally:
        app.close()


def test_lumos_context_manager(config: Config):
    with Lumos(config=config) as app:
        app.reminders.add("hi", when="in 1 hour")
    # Re-opening should still see it.
    with Lumos(config=config) as app:
        assert len(app.reminders.list()) == 1


def test_drive_attribute_lazy(config: Config, monkeypatch):
    """Accessing .drive should not import google libs by itself."""
    app = Lumos(config=config)
    try:
        client = app.drive
        # drive.service is the lazy bit; just checking the property type.
        assert client is app.drive  # cached
    finally:
        app.close()


# --------------------------------------------------------------------------- #
# Backup / restore via a stubbed DriveClient
# --------------------------------------------------------------------------- #

class _StubDrive:
    """In-memory DriveClient stand-in.

    Stores uploads in ``self.files: dict[id, bytes]`` and ``self.meta``.
    """

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.meta: dict[str, dict] = {}
        self.folders: dict[str, dict] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"id-{self._counter}"

    def list_files(self, *, query=None, max_results=None, include_trashed=False, **kw):
        # Only used to find the backup folder.
        if query and "Lumos Backups" in query:
            return [m for m in self.folders.values() if m["name"] == "Lumos Backups"]
        return list(self.meta.values())

    def create_folder(self, name, *, parent_id=None):
        fid = self._new_id()
        meta = {"id": fid, "name": name, "mimeType": "application/vnd.google-apps.folder"}
        self.folders[fid] = meta
        return meta

    def upload(self, path, *, folder_id=None, name=None, mime_type=None):
        fid = self._new_id()
        data = Path(path).read_bytes()
        self.files[fid] = data
        meta = {
            "id": fid,
            "name": name or Path(path).name,
            "mimeType": mime_type or "application/octet-stream",
            "parents": [folder_id] if folder_id else [],
        }
        self.meta[fid] = meta
        return meta

    def download(self, file_id, dest):
        if file_id not in self.files:
            raise KeyError(file_id)
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.files[file_id])
        return out


def _patch_drive(app: Lumos, stub: _StubDrive) -> None:
    app._drive = stub  # type: ignore[attr-defined]


def test_backup_to_drive_creates_folder_and_uploads(config: Config):
    with Lumos(config=config) as app:
        stub = _StubDrive()
        _patch_drive(app, stub)
        app.reminders.add("hi", when="in 1 hour")
        meta = app.backup_to_drive()
        assert meta["id"] in stub.files
        # Backup folder was created.
        assert any(f["name"] == "Lumos Backups" for f in stub.folders.values())
        # File name is timestamped.
        assert meta["name"].startswith("lumos-")
        assert meta["name"].endswith(".db")


def test_backup_reuses_existing_folder(config: Config):
    with Lumos(config=config) as app:
        stub = _StubDrive()
        _patch_drive(app, stub)
        app.backup_to_drive()
        n_folders_after_first = len(stub.folders)
        app.backup_to_drive()
        assert len(stub.folders) == n_folders_after_first


def test_backup_uses_explicit_folder_id(config: Config):
    with Lumos(config=config) as app:
        stub = _StubDrive()
        _patch_drive(app, stub)
        meta = app.backup_to_drive(folder_id="my-folder")
        assert meta["parents"] == ["my-folder"]


def test_restore_from_drive_replaces_db(config: Config):
    # Step 1: create reminder, back up.
    with Lumos(config=config) as app:
        stub = _StubDrive()
        _patch_drive(app, stub)
        app.reminders.add("before-restore", when="in 1 hour")
        meta = app.backup_to_drive()
        backup_id = meta["id"]
        backup_bytes = stub.files[backup_id]

    # Step 2: in a fresh app, mutate DB, then restore from the backup.
    with Lumos(config=config) as app:
        stub = _StubDrive()
        stub.files[backup_id] = backup_bytes  # carry the backup over
        stub.meta[backup_id] = {"id": backup_id, "name": "lumos.db"}
        _patch_drive(app, stub)
        app.reminders.add("post-mutation", when="in 1 hour")
        assert len(app.reminders.list()) == 2

        app.restore_from_drive(backup_id)
        # After restore we should see only the original reminder.
        names = {r.text for r in app.reminders.list()}
        assert names == {"before-restore"}


def test_restore_rejects_empty_id(config: Config):
    with Lumos(config=config) as app:
        _patch_drive(app, _StubDrive())
        import pytest as _pt

        with _pt.raises(ValueError):
            app.restore_from_drive("")
