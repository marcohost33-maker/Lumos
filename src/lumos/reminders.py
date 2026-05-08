"""Reminder model and service.

All due dates are stored as timezone-aware UTC ISO-8601 strings.
``parse_when`` accepts a few common forms:

    * absolute:        ``2026-06-01 09:00``  (naive → assumed local)
    * absolute UTC:    ``2026-06-01T09:00:00+00:00``
    * relative:        ``in 2 hours``, ``in 30 minutes``, ``in 3 days``
    * tomorrow / today + optional time:  ``tomorrow 9am``, ``today 18:00``
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator, Literal, Optional

from dateutil import parser as dateutil_parser

from .storage import Storage

Recurring = Literal["daily", "weekly", "monthly"]
_RECURRING_VALUES = ("daily", "weekly", "monthly")


# --------------------------------------------------------------------------- #
# Date parsing
# --------------------------------------------------------------------------- #

_REL_RE = re.compile(
    r"^\s*in\s+(\d+)\s+(minute|minutes|min|mins|hour|hours|h|day|days|d|week|weeks|w)\s*$",
    re.IGNORECASE,
)
_TOMORROW_RE = re.compile(r"^\s*tomorrow(?:\s+(.*))?$", re.IGNORECASE)
_TODAY_RE = re.compile(r"^\s*today(?:\s+(.*))?$", re.IGNORECASE)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    """Treat naive datetimes as local-time, then convert to UTC."""
    if dt.tzinfo is None:
        local = dt.astimezone()  # local tz
        return local.astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_time_fragment(fragment: str | None, base: datetime) -> datetime:
    """Combine a ``HH:MM`` / ``9am`` style fragment with ``base``."""
    if not fragment:
        # Default to 09:00 local time if no time given.
        local_base = base.astimezone()
        return local_base.replace(hour=9, minute=0, second=0, microsecond=0)
    parsed = dateutil_parser.parse(fragment, default=base.astimezone())
    return parsed


def parse_when(text: str, *, now: Optional[datetime] = None) -> datetime:
    """Parse a human-friendly date expression into UTC.

    Raises :class:`ValueError` for unparseable input.
    """
    if not text or not text.strip():
        raise ValueError("empty date expression")

    now = now or _now_utc()
    s = text.strip()

    # 'in N <unit>'
    m = _REL_RE.match(s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = _unit_to_delta(unit, n)
        return _ensure_aware(now + delta)

    # 'tomorrow [time]' / 'today [time]'
    m = _TOMORROW_RE.match(s)
    if m:
        base = (now.astimezone() + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return _ensure_aware(_parse_time_fragment(m.group(1), base))

    m = _TODAY_RE.match(s)
    if m:
        base = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return _ensure_aware(_parse_time_fragment(m.group(1), base))

    # Fallback: dateutil
    try:
        parsed = dateutil_parser.parse(s, default=now.astimezone())
    except (ValueError, OverflowError) as e:
        raise ValueError(f"could not parse date: {text!r}") from e
    return _ensure_aware(parsed)


def _unit_to_delta(unit: str, n: int) -> timedelta:
    if unit in ("minute", "minutes", "min", "mins"):
        return timedelta(minutes=n)
    if unit in ("hour", "hours", "h"):
        return timedelta(hours=n)
    if unit in ("day", "days", "d"):
        return timedelta(days=n)
    if unit in ("week", "weeks", "w"):
        return timedelta(weeks=n)
    raise ValueError(f"unknown time unit: {unit}")


def _add_recurrence(dt: datetime, recurring: Recurring) -> datetime:
    if recurring == "daily":
        return dt + timedelta(days=1)
    if recurring == "weekly":
        return dt + timedelta(weeks=1)
    if recurring == "monthly":
        # Add roughly one month while staying valid (e.g. Jan 31 → Feb 28).
        year = dt.year + (1 if dt.month == 12 else 0)
        month = 1 if dt.month == 12 else dt.month + 1
        # Clamp the day to the last valid day of the target month.
        day = min(dt.day, _last_day_of_month(year, month))
        return dt.replace(year=year, month=month, day=day)
    raise ValueError(f"unknown recurrence: {recurring}")


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        next_first = datetime(year + 1, 1, 1)
    else:
        next_first = datetime(year, month + 1, 1)
    return (next_first - timedelta(days=1)).day


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@dataclass
class Reminder:
    id: Optional[int]
    text: str
    due_at: datetime
    created_at: datetime = field(default_factory=_now_utc)
    completed_at: Optional[datetime] = None
    recurring: Optional[Recurring] = None
    notes: Optional[str] = None

    @property
    def is_due(self) -> bool:
        return self.completed_at is None and self.due_at <= _now_utc()

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def to_row(self) -> tuple:
        return (
            self.text,
            self.due_at.astimezone(timezone.utc).isoformat(),
            self.created_at.astimezone(timezone.utc).isoformat(),
            self.completed_at.astimezone(timezone.utc).isoformat()
            if self.completed_at
            else None,
            self.recurring,
            self.notes,
        )

    @classmethod
    def from_row(cls, row) -> "Reminder":
        return cls(
            id=row["id"],
            text=row["text"],
            due_at=datetime.fromisoformat(row["due_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
            recurring=row["recurring"],
            notes=row["notes"],
        )

    def __str__(self) -> str:
        marker = "✓" if self.is_completed else ("!" if self.is_due else " ")
        rec = f" ({self.recurring})" if self.recurring else ""
        local = self.due_at.astimezone()
        return (
            f"[{marker}] #{self.id or '?'} {self.text}"
            f" — due {local:%Y-%m-%d %H:%M}{rec}"
        )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class ReminderService:
    """CRUD + scheduling helpers for reminders."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ---- create ----------------------------------------------------------- #

    def add(
        self,
        text: str,
        *,
        when: str | datetime,
        recurring: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Reminder:
        if not text or not text.strip():
            raise ValueError("reminder text must not be empty")

        if isinstance(when, datetime):
            due_at = _ensure_aware(when)
        else:
            due_at = parse_when(when)

        rec = self._validate_recurring(recurring)

        reminder = Reminder(
            id=None,
            text=text.strip(),
            due_at=due_at,
            recurring=rec,
            notes=notes,
        )
        with self.storage.transaction() as cur:
            cur.execute(
                """
                INSERT INTO reminders
                    (text, due_at, created_at, completed_at, recurring, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                reminder.to_row(),
            )
            reminder.id = cur.lastrowid
        return reminder

    @staticmethod
    def _validate_recurring(value: Optional[str]) -> Optional[Recurring]:
        if value is None:
            return None
        v = value.lower().strip()
        if v not in _RECURRING_VALUES:
            raise ValueError(
                f"recurring must be one of {_RECURRING_VALUES}, got {value!r}"
            )
        return v  # type: ignore[return-value]

    # ---- read ------------------------------------------------------------- #

    def get(self, reminder_id: int) -> Optional[Reminder]:
        cur = self.storage.conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        )
        row = cur.fetchone()
        return Reminder.from_row(row) if row else None

    def list(
        self,
        *,
        include_completed: bool = False,
        only_due: bool = False,
        limit: Optional[int] = None,
    ) -> list[Reminder]:
        sql = "SELECT * FROM reminders"
        clauses: list[str] = []
        params: list = []
        if not include_completed:
            clauses.append("completed_at IS NULL")
        if only_due:
            clauses.append("due_at <= ?")
            params.append(_now_utc().isoformat())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY due_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        cur = self.storage.conn.execute(sql, params)
        return [Reminder.from_row(r) for r in cur.fetchall()]

    def due(self) -> list[Reminder]:
        return self.list(only_due=True)

    def __iter__(self) -> Iterator[Reminder]:
        return iter(self.list(include_completed=True))

    # ---- update ----------------------------------------------------------- #

    def complete(self, reminder_id: int) -> Reminder:
        """Mark as completed. Recurring reminders roll forward instead.

        Returns the resulting reminder (the rescheduled one for recurring
        items, or the just-completed one otherwise).
        """
        existing = self._require(reminder_id)
        if existing.completed_at is not None:
            return existing

        now = _now_utc()
        if existing.recurring:
            new_due = _add_recurrence(existing.due_at, existing.recurring)
            # Roll forward past 'now' for very stale reminders.
            while new_due <= now:
                new_due = _add_recurrence(new_due, existing.recurring)
            with self.storage.transaction() as cur:
                cur.execute(
                    "UPDATE reminders SET due_at = ? WHERE id = ?",
                    (new_due.isoformat(), reminder_id),
                )
            existing.due_at = new_due
            return existing

        with self.storage.transaction() as cur:
            cur.execute(
                "UPDATE reminders SET completed_at = ? WHERE id = ?",
                (now.isoformat(), reminder_id),
            )
        existing.completed_at = now
        return existing

    def snooze(self, reminder_id: int, *, minutes: int = 0, hours: int = 0,
               days: int = 0) -> Reminder:
        if minutes == 0 and hours == 0 and days == 0:
            raise ValueError("snooze requires a non-zero duration")
        existing = self._require(reminder_id)
        if existing.completed_at is not None:
            raise ValueError(f"reminder #{reminder_id} is already completed")
        delta = timedelta(minutes=minutes, hours=hours, days=days)
        new_due = max(existing.due_at, _now_utc()) + delta
        with self.storage.transaction() as cur:
            cur.execute(
                "UPDATE reminders SET due_at = ? WHERE id = ?",
                (new_due.isoformat(), reminder_id),
            )
        existing.due_at = new_due
        return existing

    def update_text(self, reminder_id: int, text: str) -> Reminder:
        if not text or not text.strip():
            raise ValueError("reminder text must not be empty")
        existing = self._require(reminder_id)
        with self.storage.transaction() as cur:
            cur.execute(
                "UPDATE reminders SET text = ? WHERE id = ?",
                (text.strip(), reminder_id),
            )
        existing.text = text.strip()
        return existing

    # ---- delete ----------------------------------------------------------- #

    def delete(self, reminder_id: int) -> bool:
        with self.storage.transaction() as cur:
            cur.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return cur.rowcount > 0

    def clear_completed(self) -> int:
        with self.storage.transaction() as cur:
            cur.execute("DELETE FROM reminders WHERE completed_at IS NOT NULL")
            return cur.rowcount

    # ---- helpers ---------------------------------------------------------- #

    def _require(self, reminder_id: int) -> Reminder:
        r = self.get(reminder_id)
        if r is None:
            raise KeyError(f"no reminder with id={reminder_id}")
        return r

    def bulk_add(self, items: Iterable[tuple[str, str]]) -> list[Reminder]:
        return [self.add(text, when=when) for text, when in items]
