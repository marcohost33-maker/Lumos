# Lumos

A small personal assistant with **reminders** and **Google Drive** sync,
exposed as a Python library and a `lumos` CLI.

> *"Lumos!"* — turn the lights on for what you need to remember and
> what you need to keep in sync.

## Features

- **Reminders** — create, list, snooze, complete and delete reminders with
  natural language parsing for due dates (`"tomorrow 9am"`, `"in 2 hours"`,
  `"2026-06-01 14:00"`).
- **Recurring reminders** — `daily`, `weekly`, `monthly`.
- **Persistent storage** — local SQLite database under `~/.lumos/`.
- **Google Drive integration** — list, upload, download and search files.
  OAuth credentials are loaded from `~/.lumos/credentials.json` and the
  refresh token is cached locally.
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
lumos restore <file-id>          # replaces local DB with that backup
```

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
