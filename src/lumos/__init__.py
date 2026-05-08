"""Lumos — a small personal assistant.

Public surface:
    Lumos          — application facade
    Reminder       — reminder data class
    ReminderService — reminders backend
    DriveClient    — Google Drive helper
    Config         — paths and user configuration
"""
from __future__ import annotations

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


def __getattr__(name: str):
    # Lazy import for DriveClient so importing `lumos` doesn't require
    # the optional google-api dependencies.
    if name == "DriveClient":
        from .drive import DriveClient

        return DriveClient
    raise AttributeError(name)
