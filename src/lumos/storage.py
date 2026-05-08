"""SQLite-backed persistence for Lumos.

The schema is intentionally tiny: one table per concept, an integer
``schema_version`` row, and migrations applied on connect. SQLite is
chosen because Lumos is a single-user tool — no server required.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT    NOT NULL,
    due_at      TEXT    NOT NULL,         -- ISO-8601 UTC
    created_at  TEXT    NOT NULL,
    completed_at TEXT,
    recurring   TEXT,                     -- 'daily' | 'weekly' | 'monthly' | NULL
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_open
    ON reminders(completed_at) WHERE completed_at IS NULL;
"""


class Storage:
    """Thin wrapper around a sqlite3 connection.

    The connection uses ``Row`` factory so callers get dict-like rows.
    Foreign keys are enabled for forward compatibility.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,  # autocommit; we manage txns explicitly
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self._migrate()

    def _migrate(self) -> None:
        # ``executescript`` issues its own COMMIT, so it cannot run inside an
        # explicit transaction. Run it directly, then record the schema
        # version in a normal transaction.
        self.conn.executescript(_SCHEMA)
        with self.transaction() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        cur = self.conn.cursor()
        cur.execute("BEGIN")
        try:
            yield cur
        except Exception:
            cur.execute("ROLLBACK")
            raise
        else:
            cur.execute("COMMIT")
        finally:
            cur.close()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.ProgrammingError:
            # Already closed — nothing to do.
            pass
