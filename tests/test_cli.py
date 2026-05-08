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
