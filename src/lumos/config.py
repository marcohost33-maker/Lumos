"""Lumos configuration: filesystem paths and environment overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_home() -> Path:
    override = os.environ.get("LUMOS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".lumos"


@dataclass(frozen=True)
class Config:
    """Resolved paths Lumos uses on disk.

    All paths live under a single ``home`` directory so a user can wipe
    their state with one ``rm -rf``. The directory is created lazily by
    :meth:`ensure_dirs`.
    """

    home: Path
    db_path: Path
    credentials_path: Path
    token_path: Path

    @classmethod
    def default(cls) -> "Config":
        home = _default_home()
        return cls(
            home=home,
            db_path=home / "lumos.db",
            credentials_path=home / "credentials.json",
            token_path=home / "token.json",
        )

    @classmethod
    def for_home(cls, home: os.PathLike[str] | str) -> "Config":
        h = Path(home).expanduser().resolve()
        return cls(
            home=h,
            db_path=h / "lumos.db",
            credentials_path=h / "credentials.json",
            token_path=h / "token.json",
        )

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
