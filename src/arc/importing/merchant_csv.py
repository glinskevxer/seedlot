"""Reading a merchant's list of lots.

The rule that shapes all of this: one bad row is not a bad file. A merchant who
mistypes one lot reference should get twenty three lots booked in and one line
telling them which row to fix, not a rejection of the whole thing. So parsing
never raises on a row; it returns either a lot or a reason, keyed by the line
number in the file the merchant is looking at.

Line numbers count the header, because that is what a spreadsheet shows. Row
two is the first row of data, and telling somebody their mistake is on row one
when their screen says two helps nobody.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from arc.lots.model import ContainerKind, LotReference, SeedLot
from arc.species import register

__all__ = [
    "COLUMNS",
    "RowProblem",
    "ParsedFile",
    "parse",
]

#: What the station asks merchants to send. Extra columns are ignored, because
#: merchants send their own stock codes and there is no reason to argue.
COLUMNS = (
    "lot",
    "species",
    "weight kg",
    "containers",
    "container count",
    "sealed on",
    "origin",
)


@dataclass(frozen=True)
class RowProblem:
    """One row that could not be turned into a lot, and why."""

    line: int
    detail: str
    value: str = ""

    def __str__(self) -> str:
        if self.value:
            return f"row {self.line}: {self.detail} ({self.value!r})"
        return f"row {self.line}: {self.detail}"


@dataclass(frozen=True)
class ParsedFile:
    """Everything the file turned into, good and bad."""

    lots: tuple[SeedLot, ...]
    problems: tuple[RowProblem, ...]

    @property
    def is_clean(self) -> bool:
        return not self.problems

    @property
    def rows_read(self) -> int:
        return len(self.lots) + len(self.problems)

    def summary(self) -> str:
        if self.is_clean:
            return f"{len(self.lots)} lots, no problems"
        return f"{len(self.lots)} lots, {len(self.problems)} rows to fix"


def parse(text: str, merchant: str) -> ParsedFile:
    """Turns a merchant's file into lots, keeping the failures beside them.

    The merchant's name comes from outside the file rather than out of a
    column. The file arrives attached to an email from a merchant, and letting
    a row name a different one would let a typo book a lot in against somebody
    else's account.
    """
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return ParsedFile((), (RowProblem(1, "the file is empty"),))

    missing = [name for name in COLUMNS if name not in reader.fieldnames]
    if missing:
        return ParsedFile(
            (),
            (RowProblem(1, f"these columns are missing: {', '.join(missing)}"),),
        )

    lots: list[SeedLot] = []
    problems: list[RowProblem] = []
    seen: set[str] = set()

    for line, row in enumerate(reader, start=2):
        outcome = _row_to_lot(row, merchant=merchant, line=line, seen=seen)
        if isinstance(outcome, RowProblem):
            problems.append(outcome)
        else:
            lots.append(outcome)
            seen.add(str(outcome.reference))

    return ParsedFile(tuple(lots), tuple(problems))


def _row_to_lot(
    row: dict[str, str | None],
    *,
    merchant: str,
    line: int,
    seen: set[str],
) -> SeedLot | RowProblem:
    """One row, into a lot or into a reason it is not one."""

    def value(column: str) -> str:
        return (row.get(column) or "").strip()

    reference_text = value("lot")
    try:
        reference = LotReference.parse(reference_text)
    except ValueError as bad:
        return RowProblem(line, str(bad), reference_text)

    if str(reference) in seen:
        return RowProblem(line, "this lot is already on the list", str(reference))

    species = register.find(value("species"))
    if species is None:
        return RowProblem(line, "the station does not test this species", value("species"))

    try:
        weight = Decimal(value("weight kg"))
    except InvalidOperation:
        return RowProblem(line, "the weight is not a number", value("weight kg"))
    if weight <= 0:
        return RowProblem(line, "a lot cannot weigh nothing", value("weight kg"))

    try:
        kind = ContainerKind(value("containers").lower())
    except ValueError:
        allowed = ", ".join(item.value for item in ContainerKind)
        return RowProblem(
            line,
            f"not a way of putting seed up, expected one of {allowed}",
            value("containers"),
        )

    count_text = value("container count") or "0"
    if not count_text.isdigit():
        return RowProblem(line, "the container count is not a whole number", count_text)

    try:
        sealed_on = date.fromisoformat(value("sealed on"))
    except ValueError:
        return RowProblem(line, "the sealing date is not a date", value("sealed on"))

    origin = value("origin").upper()
    if len(origin) != 2 or not origin.isalpha():
        return RowProblem(line, "the origin is not a two letter country", origin)

    try:
        return SeedLot(
            reference=reference,
            species_name=species.botanical_name,
            declared_weight_kg=weight,
            container_kind=kind,
            container_count=int(count_text),
            merchant=merchant,
            sealed_on=sealed_on,
            origin_country=origin,
        )
    except ValueError as refused:
        return RowProblem(line, str(refused))
