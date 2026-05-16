"""End-to-end CLI tests via Click's CliRunner."""
from __future__ import annotations

import json

from click.testing import CliRunner
from freezegun import freeze_time

from lumos.cli import main


def _run(args, env=None):
    runner = CliRunner()
    return runner.invoke(main, args, env=env or {}, catch_exceptions=False)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_add_and_list(tmp_path):
    home = str(tmp_path)
    r = _run(["--home", home, "remind", "add", "Buy milk", "--when", "tomorrow 09:00"])
    assert r.exit_code == 0, r.output
    assert "Added reminder" in r.output

    r = _run(["--home", home, "remind", "list"])
    assert r.exit_code == 0
    assert "Buy milk" in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_list_json(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "x", "--when", "in 1 hour"])
    r = _run(["--home", home, "remind", "list", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert len(data) == 1
    assert data[0]["text"] == "x"
    assert data[0]["recurring"] is None


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_complete_and_delete(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "a", "--when", "in 1 hour"])
    _run(["--home", home, "remind", "add", "b", "--when", "in 2 hours"])

    r = _run(["--home", home, "remind", "complete", "1"])
    assert r.exit_code == 0
    assert "completed" in r.output

    r = _run(["--home", home, "remind", "list"])
    assert "a" not in r.output
    assert "b" in r.output

    r = _run(["--home", home, "remind", "delete", "2"])
    assert r.exit_code == 0
    assert "Deleted" in r.output

    r = _run(["--home", home, "remind", "list"])
    assert r.output.strip() == "No reminders."


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_snooze(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "a", "--when", "in 1 hour"])
    r = _run(["--home", home, "remind", "snooze", "1", "--minutes", "30"])
    assert r.exit_code == 0
    assert "Snoozed" in r.output


def test_remind_add_invalid_when(tmp_path):
    r = _run(["--home", str(tmp_path), "remind", "add", "x", "--when", "garbage!!"])
    assert r.exit_code != 0
    assert "could not parse date" in r.output.lower() or "error" in r.output.lower()


def test_remind_delete_missing(tmp_path):
    r = _run(["--home", str(tmp_path), "remind", "delete", "999"])
    assert r.exit_code != 0


def test_drive_list_without_auth_errors(tmp_path):
    """No credentials → friendly error rather than a stack trace."""
    r = _run(["--home", str(tmp_path), "drive", "list"])
    assert r.exit_code != 0
    assert "Error:" in r.output


def test_help_shows_commands(tmp_path):
    r = _run(["--home", str(tmp_path), "--help"])
    assert r.exit_code == 0
    assert "remind" in r.output
    assert "drive" in r.output
    assert "backup" in r.output
    assert "status" in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_next_empty(tmp_path):
    r = _run(["--home", str(tmp_path), "remind", "next"])
    assert r.exit_code == 0
    assert "No upcoming reminders" in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_next_returns_soonest(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "later", "--when", "in 5 hours"])
    _run(["--home", home, "remind", "add", "sooner", "--when", "in 1 hour"])
    r = _run(["--home", home, "remind", "next"])
    assert "sooner" in r.output
    assert "later" not in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_today(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "today-job", "--when", "in 1 hour"])
    _run(["--home", home, "remind", "add", "later-job", "--when", "in 3 days"])
    r = _run(["--home", home, "remind", "today"])
    assert r.exit_code == 0
    assert "today-job" in r.output
    assert "later-job" not in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_today_empty(tmp_path):
    r = _run(["--home", str(tmp_path), "remind", "today"])
    assert "Nothing due today" in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_update_text_and_when(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "x", "--when", "in 1 hour"])
    r = _run(
        ["--home", home, "remind", "update", "1", "--text", "y", "--when", "in 2 hours"]
    )
    assert r.exit_code == 0
    assert "Updated #1" in r.output
    assert "y" in r.output


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_remind_update_clears_recurrence(tmp_path):
    home = str(tmp_path)
    _run(
        [
            "--home", home,
            "remind", "add", "daily-x",
            "--when", "in 1 hour",
            "--recurring", "daily",
        ]
    )
    r = _run(["--home", home, "remind", "update", "1", "--recurring", "none"])
    assert r.exit_code == 0
    r = _run(["--home", home, "remind", "list", "--json"])
    import json as _json

    data = _json.loads(r.output)
    assert data[0]["recurring"] is None


def test_remind_update_requires_at_least_one_option(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "x", "--when", "in 1 hour"])
    r = _run(["--home", home, "remind", "update", "1"])
    assert r.exit_code != 0
    assert "nothing to update" in r.output.lower()


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_status_command(tmp_path):
    home = str(tmp_path)
    _run(["--home", home, "remind", "add", "a", "--when", "in 1 hour"])
    r = _run(["--home", home, "status"])
    assert r.exit_code == 0
    assert "Reminders:" in r.output
    assert "1 open" in r.output


def test_backup_keep_zero_rejected(tmp_path):
    r = _run(["--home", str(tmp_path), "backup", "--keep", "0"])
    assert r.exit_code != 0


def test_python_dash_m_lumos_works(tmp_path):
    """`python -m lumos --help` should also be a valid entry point."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "lumos", "--home", str(tmp_path), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert "remind" in proc.stdout
