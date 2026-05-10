"""Lumos command-line interface (``lumos`` entrypoint)."""
from __future__ import annotations

import json
import sys
from typing import Optional

import click

from . import Lumos, __version__
from .config import Config
from .reminders import Reminder


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _app(ctx: click.Context) -> Lumos:
    return ctx.obj["app"]


def _print_reminder(r: Reminder) -> None:
    click.echo(str(r))
    if r.notes:
        click.echo(f"      notes: {r.notes}")


def _format_drive_file(f: dict) -> str:
    name = f.get("name", "?")
    fid = f.get("id", "?")
    mt = f.get("mimeType", "")
    modified = f.get("modifiedTime", "")
    size = f.get("size")
    size_str = f" {int(size):>9}b" if size and str(size).isdigit() else ""
    return f"{fid}  {name}  [{mt}]  {modified}{size_str}"


# --------------------------------------------------------------------------- #
# Root command
# --------------------------------------------------------------------------- #

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--home",
    type=click.Path(file_okay=False, path_type=str),
    default=None,
    help="Override Lumos data directory (default: ~/.lumos or $LUMOS_HOME).",
)
@click.version_option(__version__, prog_name="lumos")
@click.pass_context
def main(ctx: click.Context, home: Optional[str]) -> None:
    """Lumos — reminders & Google Drive sync."""
    config = Config.for_home(home) if home else Config.default()
    app = Lumos(config=config)
    ctx.obj = {"app": app}
    ctx.call_on_close(app.close)


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #

@main.group("remind", help="Manage reminders.")
def remind_group() -> None:
    pass


@remind_group.command("add")
@click.argument("text")
@click.option("--when", "-w", required=True, help="Due date, e.g. 'tomorrow 9am'.")
@click.option(
    "--recurring",
    "-r",
    type=click.Choice(["daily", "weekly", "monthly"]),
    default=None,
)
@click.option("--notes", "-n", default=None)
@click.pass_context
def remind_add(
    ctx: click.Context,
    text: str,
    when: str,
    recurring: Optional[str],
    notes: Optional[str],
) -> None:
    """Add a new reminder."""
    try:
        r = _app(ctx).reminders.add(
            text, when=when, recurring=recurring, notes=notes
        )
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"Added reminder #{r.id}.")
    _print_reminder(r)


@remind_group.command("list")
@click.option("--all", "show_all", is_flag=True, help="Include completed.")
@click.option("--due", "only_due", is_flag=True, help="Only currently due reminders.")
@click.option("--limit", type=int, default=None)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of text.")
@click.pass_context
def remind_list(
    ctx: click.Context,
    show_all: bool,
    only_due: bool,
    limit: Optional[int],
    as_json: bool,
) -> None:
    """List reminders."""
    items = _app(ctx).reminders.list(
        include_completed=show_all, only_due=only_due, limit=limit
    )
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "text": r.text,
                        "due_at": r.due_at.isoformat(),
                        "completed_at": r.completed_at.isoformat()
                        if r.completed_at
                        else None,
                        "recurring": r.recurring,
                        "notes": r.notes,
                    }
                    for r in items
                ],
                indent=2,
            )
        )
        return
    if not items:
        click.echo("No reminders.")
        return
    for r in items:
        _print_reminder(r)


@remind_group.command("complete")
@click.argument("reminder_id", type=int)
@click.pass_context
def remind_complete(ctx: click.Context, reminder_id: int) -> None:
    """Mark a reminder as completed (or roll forward if recurring)."""
    try:
        r = _app(ctx).reminders.complete(reminder_id)
    except KeyError as e:
        raise click.ClickException(str(e))
    if r.recurring and not r.is_completed:
        click.echo(f"Reminder #{r.id} rolled forward.")
    else:
        click.echo(f"Reminder #{r.id} completed.")
    _print_reminder(r)


@remind_group.command("snooze")
@click.argument("reminder_id", type=int)
@click.option("--minutes", type=int, default=0)
@click.option("--hours", type=int, default=0)
@click.option("--days", type=int, default=0)
@click.pass_context
def remind_snooze(
    ctx: click.Context,
    reminder_id: int,
    minutes: int,
    hours: int,
    days: int,
) -> None:
    """Snooze a reminder by a duration."""
    try:
        r = _app(ctx).reminders.snooze(
            reminder_id, minutes=minutes, hours=hours, days=days
        )
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Snoozed #{r.id}.")
    _print_reminder(r)


@remind_group.command("delete")
@click.argument("reminder_id", type=int)
@click.pass_context
def remind_delete(ctx: click.Context, reminder_id: int) -> None:
    """Delete a reminder."""
    if _app(ctx).reminders.delete(reminder_id):
        click.echo(f"Deleted #{reminder_id}.")
    else:
        raise click.ClickException(f"no reminder with id={reminder_id}")


@remind_group.command("clear-completed")
@click.pass_context
def remind_clear_completed(ctx: click.Context) -> None:
    """Remove all completed reminders."""
    n = _app(ctx).reminders.clear_completed()
    click.echo(f"Removed {n} completed reminder(s).")


@remind_group.command("next")
@click.pass_context
def remind_next(ctx: click.Context) -> None:
    """Show the soonest-upcoming reminder."""
    r = _app(ctx).reminders.next_due()
    if r is None:
        click.echo("No upcoming reminders.")
        return
    _print_reminder(r)


@remind_group.command("today")
@click.option("--all", "show_all", is_flag=True, help="Include completed.")
@click.pass_context
def remind_today(ctx: click.Context, show_all: bool) -> None:
    """List reminders due before tomorrow (local time)."""
    from datetime import datetime, time, timedelta, timezone

    now_local = datetime.now().astimezone()
    tomorrow_start_local = (
        (now_local + timedelta(days=1))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    tomorrow_utc = tomorrow_start_local.astimezone(timezone.utc)
    items = _app(ctx).reminders.in_window(
        before=tomorrow_utc, include_completed=show_all
    )
    if not items:
        click.echo("Nothing due today.")
        return
    for r in items:
        _print_reminder(r)


@remind_group.command("update")
@click.argument("reminder_id", type=int)
@click.option("--text", "-t", default=None, help="New text.")
@click.option("--when", "-w", default=None, help="New due date.")
@click.option(
    "--recurring",
    "-r",
    type=click.Choice(["daily", "weekly", "monthly", "none"]),
    default=None,
    help="Set or clear ('none') recurrence.",
)
@click.option("--notes", "-n", default=None, help="Replace notes.")
@click.option("--clear-notes", is_flag=True, help="Drop existing notes.")
@click.pass_context
def remind_update(
    ctx: click.Context,
    reminder_id: int,
    text: Optional[str],
    when: Optional[str],
    recurring: Optional[str],
    notes: Optional[str],
    clear_notes: bool,
) -> None:
    """Update one or more fields of a reminder."""
    svc = _app(ctx).reminders
    kwargs: dict = {}
    if text is not None:
        kwargs["text"] = text
    if when is not None:
        kwargs["when"] = when
    if recurring is not None:
        kwargs["recurring"] = None if recurring == "none" else recurring
    if clear_notes:
        kwargs["notes"] = None
    elif notes is not None:
        kwargs["notes"] = notes

    if not kwargs:
        raise click.ClickException("nothing to update — pass at least one option")

    try:
        r = svc.update(reminder_id, **kwargs)
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Updated #{r.id}.")
    _print_reminder(r)


# --------------------------------------------------------------------------- #
# Drive
# --------------------------------------------------------------------------- #

@main.group("drive", help="Google Drive integration.")
def drive_group() -> None:
    pass


@drive_group.command("auth")
@click.option("--headless", is_flag=True, help="Use console flow (no browser).")
@click.pass_context
def drive_auth(ctx: click.Context, headless: bool) -> None:
    """Run the Google OAuth flow and cache credentials."""
    from .drive import DriveError

    try:
        _app(ctx).drive.authenticate(headless=headless)
    except DriveError as e:
        raise click.ClickException(str(e))
    click.echo("Authenticated. Token cached.")


@drive_group.command("list")
@click.option("--query", "-q", default=None, help="Drive query string.")
@click.option("--limit", type=int, default=25)
@click.option(
    "--include-trashed",
    is_flag=True,
    help="Also include files in the trash (default: excluded).",
)
@click.pass_context
def drive_list(
    ctx: click.Context,
    query: Optional[str],
    limit: int,
    include_trashed: bool,
) -> None:
    """List Drive files."""
    from .drive import DriveError

    try:
        files = _app(ctx).drive.list_files(
            query=query, max_results=limit, include_trashed=include_trashed
        )
    except DriveError as e:
        raise click.ClickException(str(e))
    if not files:
        click.echo("No files.")
        return
    for f in files:
        click.echo(_format_drive_file(f))


@drive_group.command("search")
@click.argument("name_contains")
@click.option("--limit", type=int, default=25)
@click.pass_context
def drive_search(ctx: click.Context, name_contains: str, limit: int) -> None:
    """Search Drive by file name substring."""
    from .drive import DriveError

    try:
        files = _app(ctx).drive.search(name_contains, max_results=limit)
    except DriveError as e:
        raise click.ClickException(str(e))
    if not files:
        click.echo("No files.")
        return
    for f in files:
        click.echo(_format_drive_file(f))


@drive_group.command("upload")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--folder-id", default=None)
@click.option("--name", default=None)
@click.option("--mime-type", default=None)
@click.pass_context
def drive_upload(
    ctx: click.Context,
    path: str,
    folder_id: Optional[str],
    name: Optional[str],
    mime_type: Optional[str],
) -> None:
    """Upload a local file to Drive."""
    from .drive import DriveError

    try:
        meta = _app(ctx).drive.upload(
            path, folder_id=folder_id, name=name, mime_type=mime_type
        )
    except DriveError as e:
        raise click.ClickException(str(e))
    click.echo(f"Uploaded as {meta.get('id')} ({meta.get('name')}).")


@drive_group.command("download")
@click.argument("file_id")
@click.option("--out", "-o", required=True, type=click.Path(dir_okay=False))
@click.pass_context
def drive_download(ctx: click.Context, file_id: str, out: str) -> None:
    """Download a Drive file by id."""
    from .drive import DriveError

    try:
        path = _app(ctx).drive.download(file_id, out)
    except DriveError as e:
        raise click.ClickException(str(e))
    click.echo(f"Saved to {path}.")


@drive_group.command("delete")
@click.argument("file_id")
@click.confirmation_option(prompt="Really delete this file?")
@click.pass_context
def drive_delete(ctx: click.Context, file_id: str) -> None:
    """Delete a Drive file by id."""
    from .drive import DriveError

    try:
        _app(ctx).drive.delete(file_id)
    except DriveError as e:
        raise click.ClickException(str(e))
    click.echo(f"Deleted {file_id}.")


@drive_group.command("mkdir")
@click.argument("name")
@click.option("--parent-id", default=None)
@click.pass_context
def drive_mkdir(ctx: click.Context, name: str, parent_id: Optional[str]) -> None:
    """Create a folder in Drive."""
    from .drive import DriveError

    try:
        meta = _app(ctx).drive.create_folder(name, parent_id=parent_id)
    except DriveError as e:
        raise click.ClickException(str(e))
    click.echo(f"Created folder {meta.get('id')} ({meta.get('name')}).")


# --------------------------------------------------------------------------- #
# Backup / restore (bridges reminders + Drive)
# --------------------------------------------------------------------------- #

@main.command("backup")
@click.option(
    "--folder-id",
    default=None,
    help="Drive folder id (default: a 'Lumos Backups' folder at root).",
)
@click.option(
    "--keep",
    type=int,
    default=None,
    help="Keep only the most recent N backups (delete older ones after upload).",
)
@click.pass_context
def backup_cmd(
    ctx: click.Context, folder_id: Optional[str], keep: Optional[int]
) -> None:
    """Upload the local SQLite DB to Google Drive as a timestamped backup."""
    from .drive import DriveError

    try:
        meta = _app(ctx).backup_to_drive(folder_id=folder_id, keep=keep)
    except (DriveError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Backed up as {meta.get('name')} (id={meta.get('id')}).")


@main.command("restore")
@click.argument("file_id")
@click.confirmation_option(
    prompt="This will replace your local Lumos database. Continue?"
)
@click.pass_context
def restore_cmd(ctx: click.Context, file_id: str) -> None:
    """Replace local DB with a backup from Drive."""
    from .drive import DriveError

    try:
        path = _app(ctx).restore_from_drive(file_id)
    except (DriveError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Restored to {path}.")


@main.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Show a brief status summary."""
    app = _app(ctx)
    total = len(app.reminders.list(include_completed=True))
    open_ = len(app.reminders.list(include_completed=False))
    due = len(app.reminders.due())
    nxt = app.reminders.next_due()
    click.echo(f"Home:           {app.config.home}")
    click.echo(f"Reminders:      {open_} open ({total} total)")
    click.echo(f"Due now:        {due}")
    if nxt is not None:
        click.echo(f"Next:           {nxt}")
    else:
        click.echo("Next:           —")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
