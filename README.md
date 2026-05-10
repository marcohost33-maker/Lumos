# Lumos

A small personal assistant with **reminders** and **Google Drive** sync,
exposed as a Python library and a `lumos` CLI.

> *"Lumos!"* — turn the lights on for what you need to remember and
> what you need to keep in sync.

## Features

- **Reminders** — create, list, snooze, complete, update and delete
  reminders with natural-language parsing for due dates (`"tomorrow 9am"`,
  `"in 2 hours"`, `"2026-06-01 14:00"`).
- **Recurring reminders** — `daily`, `weekly`, `monthly`. Monthly clamps
  to month-end (Jan 31 → Feb 28). Completing rolls forward.
- **Persistent storage** — local SQLite database under `~/.lumos/`,
  configured with WAL + `synchronous=NORMAL` for a good durability /
  performance tradeoff.
- **Google Drive integration** — list, upload, download (with native
  Google Workspace export), delete and search files. Uses the **narrow
  `drive.file` scope** so Lumos only ever sees its own files. OAuth
  tokens are cached locally with a **0600 atomic write**. All API calls
  retry transient errors (429 / 5xx) with **exponential backoff + jitter**.
- **Backup / restore** — one command to push your reminders DB to Drive
  and restore from there (`lumos backup` / `lumos restore`), with
  optional retention (`--keep N`).
- **Offline-friendly** — every Drive operation is wrapped in a clean
  `DriveClient` abstraction; tests run without network access.

## Install

```bash
pip install -e .[dev,gdrive]
```

The `gdrive` extra is optional — Lumos works without it (Drive commands
will print a helpful error if the libraries are missing).

## Quick start

```bash
# Reminders
lumos remind add "Pay rent" --when "2026-06-01 09:00" --recurring monthly
lumos remind list
lumos remind list --due
lumos remind today               # everything due before tomorrow
lumos remind next                # the soonest reminder
lumos remind update 1 --text "Pay rent (transfer)" --when "in 1 day"
lumos remind complete 1
lumos remind snooze 2 --minutes 30
lumos remind delete 3
lumos status                     # one-line summary

# Google Drive
lumos drive auth                 # one-time OAuth flow
lumos drive list --query "name contains 'report'"
lumos drive upload ./notes.md --folder-id <id>
lumos drive download <file-id> --out ./notes.md

# Bridge: back up reminders DB to Drive and restore later
lumos backup                     # uploads to a 'Lumos Backups' folder
lumos backup --keep 7            # keep only the 7 most recent backups
lumos restore <file-id>          # replaces local DB with that backup
```

### Drive scope note

Lumos requests the `https://www.googleapis.com/auth/drive.file` scope —
it can only see files it created or that the user explicitly shared with
it. This is the scope Google recommends for app-specific use; it avoids
the heavyweight Google verification process. If you previously authorized
Lumos with the broader `drive` scope, delete `~/.lumos/token.json` and
re-run `lumos drive auth`.

Lumos is also runnable as a module: `python -m lumos --help`.

## Programmatic use

```python
from lumos import Lumos

app = Lumos()
app.reminders.add("Call mum", when="tomorrow 18:00")
for r in app.reminders.due():
    print(r)
```

## Layout

```
src/lumos/
  __init__.py        # public API: Lumos, Reminder, DriveClient
  config.py          # paths & user config
  storage.py         # SQLite backend
  reminders.py       # Reminder model + ReminderService
  drive.py           # DriveClient (Google Drive)
  cli.py             # `lumos` command
tests/               # pytest suite (no network required)
```

## License

MIT
