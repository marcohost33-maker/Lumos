"""Lumos — a small personal assistant.

Public surface:
    Lumos          — application facade
    Reminder       — reminder data class
    ReminderService — reminders backend
    DriveClient    — Google Drive helper
    Config         — paths and user configuration
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config
from .reminders import Reminder, ReminderService
from .storage import Storage

__all__ = [
    "Lumos",
    "Config",
    "Reminder",
    "ReminderService",
    "Storage",
    "DriveClient",
    "__version__",
]

__version__ = "0.1.0"

_BACKUP_FOLDER_NAME = "Lumos Backups"


class Lumos:
    """Top-level facade tying together storage, reminders and Drive."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.default()
        self.config.ensure_dirs()
        self.storage = Storage(self.config.db_path)
        self.reminders = ReminderService(self.storage)

    @property
    def drive(self):
        """Lazily construct a DriveClient. Imported lazily so that the
        google-api libraries are only required if the user actually
        touches Drive."""
        from .drive import DriveClient

        if not hasattr(self, "_drive"):
            self._drive = DriveClient(self.config)
        return self._drive

    def close(self) -> None:
        self.storage.close()

    def __enter__(self) -> "Lumos":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Backup / restore — bridges reminders + Drive
    # ------------------------------------------------------------------ #

    def backup_to_drive(
        self,
        *,
        folder_id: Optional[str] = None,
        keep: Optional[int] = None,
    ) -> dict:
        """Upload the current SQLite DB as a timestamped file to Drive.

        If ``folder_id`` is None, a folder named ``Lumos Backups`` is
        created (or reused) at the Drive root and used as the target.
        If ``keep`` is provided, older Lumos backups in that folder
        beyond the most recent ``keep`` are deleted after the new upload
        succeeds.

        Returns the uploaded file's metadata.
        """
        if keep is not None and keep < 1:
            raise ValueError("keep must be >= 1")

        # Ensure on-disk DB reflects in-memory writes (WAL checkpoint).
        try:
            self.storage.conn.execute("PRAGMA wal_checkpoint(FULL);")
        except Exception:
            pass

        if folder_id is None:
            folder_id = self._ensure_backup_folder()

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        meta = self.drive.upload(
            self.config.db_path,
            folder_id=folder_id,
            name=f"lumos-{ts}.db",
            mime_type="application/x-sqlite3",
        )

        if keep is not None:
            self._prune_backups(folder_id, keep=keep)

        return meta

    def _prune_backups(self, folder_id: str, *, keep: int) -> list[str]:
        """Delete older ``lumos-*.db`` backups in ``folder_id`` past ``keep``.

        Returns the ids that were deleted. Failures to delete individual
        items are logged and swallowed — losing a stale backup is much
        better than crashing in the middle of cleanup.
        """
        # Escape the folder id for the Drive query.
        safe_id = folder_id.replace("\\", "\\\\").replace("'", "\\'")
        files = self.drive.list_files(
            query=(
                f"'{safe_id}' in parents and "
                "name contains 'lumos-' and "
                "mimeType != 'application/vnd.google-apps.folder'"
            ),
            fields="id, name, createdTime, modifiedTime",
        )
        # Drive returns no guaranteed order; sort newest-first.
        files.sort(
            key=lambda f: (f.get("modifiedTime") or f.get("createdTime") or ""),
            reverse=True,
        )
        deleted: list[str] = []
        for stale in files[keep:]:
            try:
                self.drive.delete(stale["id"])
                deleted.append(stale["id"])
            except Exception as e:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "could not prune backup %s (%s): %s", stale.get("id"), stale.get("name"), e
                )
        return deleted

    def restore_from_drive(self, file_id: str) -> Path:
        """Download a backup from Drive and replace the local DB.

        Closes the active storage connection, downloads to ``db_path``
        atomically, then reopens. Returns the DB path.
        """
        if not file_id:
            raise ValueError("file_id must not be empty")

        tmp = self.config.db_path.with_suffix(".db.restore-tmp")
        self.drive.download(file_id, tmp)

        # Swap atomically: close current conn, replace file, reopen.
        self.storage.close()
        # Best-effort cleanup of WAL sidecars — they belong to the old DB.
        for sfx in (".wal", ".shm"):
            sidecar = self.config.db_path.with_suffix(self.config.db_path.suffix + sfx)
            if sidecar.exists():
                sidecar.unlink()
        tmp.replace(self.config.db_path)
        self.storage = Storage(self.config.db_path)
        self.reminders = ReminderService(self.storage)
        return self.config.db_path

    def _ensure_backup_folder(self) -> str:
        existing = self.drive.list_files(
            query=(
                f"name = '{_BACKUP_FOLDER_NAME}' and "
                "mimeType = 'application/vnd.google-apps.folder'"
            ),
            max_results=1,
        )
        if existing:
            return existing[0]["id"]
        return self.drive.create_folder(_BACKUP_FOLDER_NAME)["id"]


def __getattr__(name: str):
    # Lazy import for DriveClient so importing `lumos` doesn't require
    # the optional google-api dependencies.
    if name == "DriveClient":
        from .drive import DriveClient

        return DriveClient
    raise AttributeError(name)
