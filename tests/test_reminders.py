from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from lumos.reminders import (
    Reminder,
    ReminderService,
    _add_recurrence,
    _last_day_of_month,
    parse_when,
)


# --------------------------------------------------------------------------- #
# parse_when
# --------------------------------------------------------------------------- #

@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_relative_minutes():
    dt = parse_when("in 30 minutes")
    assert dt.tzinfo is not None
    assert dt - datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc) == timedelta(minutes=30)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_relative_hours():
    dt = parse_when("in 2 hours")
    assert dt == datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_relative_days_short():
    dt = parse_when("in 3 d")
    assert dt == datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_tomorrow_default_time():
    # No time given → 09:00 local. With TZ=UTC fixture, that's 09:00 UTC.
    dt = parse_when("tomorrow")
    assert dt == datetime(2026, 5, 9, 9, 0, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_tomorrow_with_time():
    dt = parse_when("tomorrow 18:30")
    assert dt == datetime(2026, 5, 9, 18, 30, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_parse_when_today_with_time():
    dt = parse_when("today 23:00")
    assert dt == datetime(2026, 5, 8, 23, 0, tzinfo=timezone.utc)


def test_parse_when_iso():
    dt = parse_when("2026-06-01T09:00:00+00:00")
    assert dt == datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


def test_parse_when_rejects_empty():
    with pytest.raises(ValueError):
        parse_when("")


def test_parse_when_rejects_garbage():
    with pytest.raises(ValueError):
        parse_when("not a date at all !!")


# --------------------------------------------------------------------------- #
# Recurrence helpers
# --------------------------------------------------------------------------- #

def test_add_recurrence_daily():
    base = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    assert _add_recurrence(base, "daily") == base + timedelta(days=1)


def test_add_recurrence_weekly():
    base = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    assert _add_recurrence(base, "weekly") == base + timedelta(weeks=1)


def test_add_recurrence_monthly_clamps_day():
    base = datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    nxt = _add_recurrence(base, "monthly")
    assert nxt.year == 2026 and nxt.month == 2
    assert nxt.day == 28  # Feb 2026


def test_add_recurrence_monthly_year_rolls_over():
    base = datetime(2026, 12, 5, 0, 0, tzinfo=timezone.utc)
    nxt = _add_recurrence(base, "monthly")
    assert nxt.year == 2027 and nxt.month == 1 and nxt.day == 5


def test_last_day_of_month_basics():
    assert _last_day_of_month(2026, 2) == 28
    assert _last_day_of_month(2024, 2) == 29  # leap
    assert _last_day_of_month(2026, 12) == 31


# --------------------------------------------------------------------------- #
# Reminder model round-trip
# --------------------------------------------------------------------------- #

def test_reminder_to_row_round_trip():
    due = datetime(2026, 5, 9, 9, 0, tzinfo=timezone.utc)
    created = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    r = Reminder(
        id=None,
        text="hi",
        due_at=due,
        created_at=created,
        completed_at=None,
        recurring="daily",
        notes="n",
    )
    text, due_iso, created_iso, completed_iso, recurring, notes = r.to_row()
    assert text == "hi"
    assert due_iso == due.isoformat()
    assert created_iso == created.isoformat()
    assert completed_iso is None
    assert recurring == "daily"
    assert notes == "n"


# --------------------------------------------------------------------------- #
# ReminderService
# --------------------------------------------------------------------------- #

@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_add_and_list(app):
    r = app.reminders.add("Pay rent", when="tomorrow 09:00")
    assert r.id is not None
    assert r.text == "Pay rent"
    assert r.due_at == datetime(2026, 5, 9, 9, 0, tzinfo=timezone.utc)

    items = app.reminders.list()
    assert [x.id for x in items] == [r.id]


def test_add_rejects_empty_text(app):
    with pytest.raises(ValueError):
        app.reminders.add("   ", when="in 1 hour")


def test_add_rejects_bad_recurring(app):
    with pytest.raises(ValueError):
        app.reminders.add("x", when="in 1 hour", recurring="yearly")


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_only_due_filter(app):
    past = app.reminders.add("past", when="in 0 minutes")  # exactly now ⇒ due
    future = app.reminders.add("future", when="in 1 hour")
    due_ids = {r.id for r in app.reminders.due()}
    assert past.id in due_ids
    assert future.id not in due_ids


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_complete_non_recurring(app):
    r = app.reminders.add("once", when="in 1 hour")
    completed = app.reminders.complete(r.id)
    assert completed.is_completed
    # No longer in default list
    assert app.reminders.list() == []
    # But appears with include_completed
    assert len(app.reminders.list(include_completed=True)) == 1


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_complete_recurring_rolls_forward(app):
    r = app.reminders.add("daily standup", when="today 09:00", recurring="daily")
    # Was due at 9am, now is noon → completing should push to tomorrow 9am
    rolled = app.reminders.complete(r.id)
    assert not rolled.is_completed
    assert rolled.due_at == datetime(2026, 5, 9, 9, 0, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_complete_recurring_skips_stale(app):
    r = app.reminders.add(
        "weekly", when="2026-04-01T09:00:00+00:00", recurring="weekly"
    )
    rolled = app.reminders.complete(r.id)
    assert rolled.due_at > datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_complete_idempotent(app):
    r = app.reminders.add("once", when="in 1 hour")
    a = app.reminders.complete(r.id)
    b = app.reminders.complete(r.id)
    assert a.completed_at == b.completed_at


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_snooze(app):
    r = app.reminders.add("call", when="in 1 hour")
    snoozed = app.reminders.snooze(r.id, minutes=30)
    expected = r.due_at + timedelta(minutes=30)
    assert snoozed.due_at == expected


def test_snooze_zero_rejected(app):
    r = app.reminders.add("call", when="in 1 hour")
    with pytest.raises(ValueError):
        app.reminders.snooze(r.id)


def test_snooze_completed_rejected(app):
    r = app.reminders.add("call", when="in 1 hour")
    app.reminders.complete(r.id)
    with pytest.raises(ValueError):
        app.reminders.snooze(r.id, minutes=10)


def test_delete_returns_bool(app):
    r = app.reminders.add("call", when="in 1 hour")
    assert app.reminders.delete(r.id) is True
    assert app.reminders.delete(r.id) is False


def test_get_missing_returns_none(app):
    assert app.reminders.get(999) is None


def test_complete_missing_raises(app):
    with pytest.raises(KeyError):
        app.reminders.complete(999)


def test_clear_completed(app):
    a = app.reminders.add("a", when="in 1 hour")
    b = app.reminders.add("b", when="in 2 hours")
    app.reminders.complete(a.id)
    n = app.reminders.clear_completed()
    assert n == 1
    assert {x.id for x in app.reminders.list(include_completed=True)} == {b.id}


def test_update_text(app):
    r = app.reminders.add("typo", when="in 1 hour")
    updated = app.reminders.update_text(r.id, "fixed")
    assert updated.text == "fixed"
    assert app.reminders.get(r.id).text == "fixed"


def test_update_text_empty_rejected(app):
    r = app.reminders.add("x", when="in 1 hour")
    with pytest.raises(ValueError):
        app.reminders.update_text(r.id, "  ")


def test_bulk_add(app):
    items = app.reminders.bulk_add([
        ("a", "in 1 hour"),
        ("b", "in 2 hours"),
    ])
    assert len(items) == 2
    assert {i.text for i in items} == {"a", "b"}


def test_str_renders_marker(app):
    r = app.reminders.add("hello", when="in 1 hour")
    assert "hello" in str(r)
    assert f"#{r.id}" in str(r)


# --------------------------------------------------------------------------- #
# update / next_due / in_window
# --------------------------------------------------------------------------- #

@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_text_via_update(app):
    r = app.reminders.add("typo", when="in 1 hour")
    updated = app.reminders.update(r.id, text="fixed")
    assert updated.text == "fixed"
    assert app.reminders.get(r.id).text == "fixed"


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_when(app):
    r = app.reminders.add("call", when="in 1 hour")
    updated = app.reminders.update(r.id, when="in 5 hours")
    assert updated.due_at == datetime(2026, 5, 8, 17, 0, tzinfo=timezone.utc)
    assert app.reminders.get(r.id).due_at == updated.due_at


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_clears_recurring(app):
    r = app.reminders.add("daily", when="today 09:00", recurring="daily")
    updated = app.reminders.update(r.id, recurring=None)
    assert updated.recurring is None
    assert app.reminders.get(r.id).recurring is None


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_clears_notes(app):
    r = app.reminders.add("call", when="in 1 hour", notes="ring twice")
    updated = app.reminders.update(r.id, notes=None)
    assert updated.notes is None
    assert app.reminders.get(r.id).notes is None


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_noop_returns_existing(app):
    r = app.reminders.add("call", when="in 1 hour")
    same = app.reminders.update(r.id)
    assert same.id == r.id


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_rejects_empty_text(app):
    r = app.reminders.add("x", when="in 1 hour")
    with pytest.raises(ValueError):
        app.reminders.update(r.id, text="   ")


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_update_rejects_bad_recurring(app):
    r = app.reminders.add("x", when="in 1 hour")
    with pytest.raises(ValueError):
        app.reminders.update(r.id, recurring="yearly")


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_next_due_returns_soonest(app):
    later = app.reminders.add("later", when="in 5 hours")
    sooner = app.reminders.add("sooner", when="in 1 hour")
    nxt = app.reminders.next_due()
    assert nxt is not None and nxt.id == sooner.id


def test_next_due_none_when_empty(app):
    assert app.reminders.next_due() is None


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_next_due_excludes_completed(app):
    r = app.reminders.add("done", when="in 1 hour")
    app.reminders.complete(r.id)
    assert app.reminders.next_due() is None


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_in_window(app):
    a = app.reminders.add("a", when="in 1 hour")     # 13:00
    b = app.reminders.add("b", when="in 25 hours")   # tomorrow 13:00
    c = app.reminders.add("c", when="in 2 hours")    # 14:00
    before = datetime(2026, 5, 8, 23, 59, tzinfo=timezone.utc)
    items = app.reminders.in_window(before=before)
    ids = {x.id for x in items}
    assert a.id in ids and c.id in ids
    assert b.id not in ids


@freeze_time("2026-05-08 12:00:00", tz_offset=0)
def test_in_window_with_after(app):
    app.reminders.add("a", when="in 1 minute")
    b = app.reminders.add("b", when="in 1 hour")
    before = datetime(2026, 5, 8, 23, 59, tzinfo=timezone.utc)
    after = datetime(2026, 5, 8, 12, 30, tzinfo=timezone.utc)
    items = app.reminders.in_window(before=before, after=after)
    assert [x.id for x in items] == [b.id]
