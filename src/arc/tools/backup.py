"""Taking a copy of the database while people are using it.

Copying the file with cp is the thing everybody does and it is wrong: SQLite
may have pages in the write ahead log that the main file does not have yet, so
the copy is a database from halfway through somebody's certificate. The backup
API walks the pages properly and holds a read lock while it does, which is why
this is nine lines of code rather than a shell command in a cron job.

The copy is checked before it is called a backup. A backup nobody has opened is
a hope, and the day it matters is the day nobody has time to find out.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from arc.storage.schema import MIGRATIONS, applied_versions, connect

__all__ = ["BackupResult", "backup_to", "verify"]


@dataclass(frozen=True)
class BackupResult:
    """Where the copy went and what was in it."""

    path: Path
    pages_copied: int
    bytes_written: int
    verified: bool

    def describe(self) -> str:
        return (
            f"{self.path} ({self.bytes_written} bytes, {self.pages_copied} pages, "
            f"{'verified' if self.verified else 'NOT VERIFIED'})"
        )


def dated_name(on: date, stem: str = "arc") -> str:
    """What a backup taken on that day is called."""
    return f"{stem}-{on.isoformat()}.sqlite3"


def backup_to(
    connection: sqlite3.Connection,
    destination: Path,
    *,
    overwrite: bool = False,
) -> BackupResult:
    """Copies the live database to a file and opens the result to check it."""
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} is already there")

    destination.parent.mkdir(parents=True, exist_ok=True)

    pages = 0

    def progress(status: int, remaining: int, total: int) -> None:
        nonlocal pages
        pages = total

    copy = sqlite3.connect(destination)
    try:
        connection.backup(copy, progress=progress)
    finally:
        copy.close()

    return BackupResult(
        path=destination,
        pages_copied=pages,
        bytes_written=destination.stat().st_size,
        verified=verify(destination),
    )


def verify(path: Path) -> bool:
    """Opens a copy and checks it is a database this release could work with.

    Two questions, in the order they can fail: does SQLite think the file is
    intact, and has it taken every migration this release knows about. The
    second is what catches a copy of last release's database, which opens
    perfectly and would put the station back a version if it were restored.

    A path that is not there is not a backup, and asking about it must not
    bring one into existence. SQLite would happily create an empty database
    at the name, so the file is checked for first.
    """
    if not path.exists():
        return False

    try:
        opened = connect(path, journal_mode="delete", synchronous="off")
    except sqlite3.DatabaseError:
        return False

    try:
        integrity = opened.execute("pragma integrity_check").fetchone()[0]
        if integrity != "ok":
            return False

        expected = {migration.version for migration in MIGRATIONS}
        return expected.issubset(set(applied_versions(opened)))
    except sqlite3.DatabaseError:
        return False
    finally:
        opened.close()
