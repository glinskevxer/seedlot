"""The day book: who did what, and when.

Every other table says what is true now. A lot has a status, a jar has a
weight, a certificate has figures on it. None of them says who changed it or
when, and the question an accreditation body asks at audit is exactly that.

Kept deliberately dumb. No foreign keys, because an entry about a lot has to
survive the lot being renamed or removed, and an audit trail that can be broken
by a delete somewhere else is not one. No structure inside the detail either:
it is a sentence written by whoever wrote the command, and a schema for it
would be a schema nobody could change afterwards.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from arc.storage.codec import to_iso

__all__ = ["Entry", "Journal"]


@dataclass(frozen=True)
class Entry:
    """One thing somebody did."""

    at: datetime
    operator: str
    action: str
    subject: str
    detail: str = ""

    @property
    def on(self) -> date:
        return self.at.date()

    def describe(self) -> str:
        stamp = self.at.isoformat(sep=" ", timespec="seconds")
        line = f"{stamp} {self.operator} {self.action} {self.subject}"
        return f"{line}: {self.detail}" if self.detail else line


class Journal:
    """The day book. Appended to, never changed."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        operator: str,
        action: str,
        subject: str,
        *,
        at: datetime,
        detail: str = "",
    ) -> int:
        cursor = self._connection.execute(
            """
            insert into journal_entry (at, operator, action, subject, detail)
            values (?, ?, ?, ?, ?)
            """,
            (at.isoformat(timespec="seconds"), operator, action, subject, detail),
        )
        return int(cursor.lastrowid or 0)

    def for_subject(self, subject: str) -> tuple[Entry, ...]:
        """Everything done to one thing, oldest first."""
        rows = self._connection.execute(
            "select * from journal_entry where subject = ? order by at asc, id asc",
            (subject,),
        ).fetchall()
        return tuple(self._to_entry(row) for row in rows)

    def on_day(self, day: date) -> tuple[Entry, ...]:
        """Everything done on one day, in the order it happened.

        Matched on the date part of the timestamp rather than by parsing it
        out, because the timestamps are ISO and a string comparison on an ISO
        date is the same comparison a date would make.
        """
        prefix = to_iso(day)
        rows = self._connection.execute(
            "select * from journal_entry where at like ? order by at asc, id asc",
            (f"{prefix}%",),
        ).fetchall()
        return tuple(self._to_entry(row) for row in rows)

    def by_operator(self, operator: str) -> tuple[Entry, ...]:
        rows = self._connection.execute(
            "select * from journal_entry where operator = ? order by at asc, id asc",
            (operator,),
        ).fetchall()
        return tuple(self._to_entry(row) for row in rows)

    def latest(self, limit: int = 20) -> tuple[Entry, ...]:
        """The most recent entries, newest first."""
        rows = self._connection.execute(
            "select * from journal_entry order by at desc, id desc limit ?",
            (limit,),
        ).fetchall()
        return tuple(self._to_entry(row) for row in rows)

    def count(self) -> int:
        row = self._connection.execute("select count(*) as n from journal_entry").fetchone()
        return int(row["n"])

    @staticmethod
    def _to_entry(row: sqlite3.Row) -> Entry:
        return Entry(
            at=datetime.fromisoformat(row["at"]),
            operator=row["operator"],
            action=row["action"],
            subject=row["subject"],
            detail=row["detail"],
        )
