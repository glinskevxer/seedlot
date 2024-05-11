"""Comma separated values, written properly.

Small enough not to want a library and fiddly enough to be worth its own file.
Every value is quoted and every quote inside one is doubled, which is the rule
the format rests on and the one that gets skipped by whoever writes it inline
with a join.

A value starting with an equals, plus, minus or at sign is prefixed with an
apostrophe. A merchant who has called themselves "=Ravenscar" should not have
their name run as a formula when somebody opens the file, and a station that
emails spreadsheets to merchants has to assume they will be opened.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

__all__ = ["CsvWriter", "quote"]

NEWLINE = "\r\n"
_FORMULA_STARTS = ("=", "+", "-", "@")


def quote(value: object) -> str:
    """One value, quoted and made safe to open in a spreadsheet."""
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_STARTS:
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


class CsvWriter:
    """Builds a sheet a row at a time."""

    def __init__(self, header: Sequence[object] | None = None) -> None:
        self._rows: list[str] = []
        if header is not None:
            self.row(*header)

    def row(self, *values: object) -> CsvWriter:
        self._rows.append(",".join(quote(value) for value in values))
        return self

    def rows(self, values: Iterable[Sequence[object]]) -> CsvWriter:
        for row in values:
            self.row(*row)
        return self

    def to_csv(self) -> str:
        if not self._rows:
            return ""
        return NEWLINE.join(self._rows) + NEWLINE

    def __len__(self) -> int:
        return len(self._rows)
