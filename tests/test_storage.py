from lumos.storage import SCHEMA_VERSION, Storage


def test_migrate_creates_tables(tmp_path):
    s = Storage(tmp_path / "x.db")
    try:
        rows = {
            r["name"]
            for r in s.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"meta", "reminders"}.issubset(rows)
        cur = s.conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        )
        assert cur.fetchone()["value"] == str(SCHEMA_VERSION)
    finally:
        s.close()


def test_transaction_rolls_back_on_error(tmp_path):
    s = Storage(tmp_path / "tx.db")
    try:
        try:
            with s.transaction() as cur:
                cur.execute(
                    "INSERT INTO reminders (text, due_at, created_at) "
                    "VALUES (?, ?, ?)",
                    ("x", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
                )
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        cur = s.conn.execute("SELECT COUNT(*) AS n FROM reminders")
        assert cur.fetchone()["n"] == 0
    finally:
        s.close()


def test_close_is_idempotent(tmp_path):
    s = Storage(tmp_path / "c.db")
    s.close()
    s.close()  # no exception
