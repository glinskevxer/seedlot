"""Whether two counts of the same thing agree.

Counting is not weighing and the allowance does not behave like the purity one.
Finding four wild oat seeds and then finding seven in a second working sample
is not a mistake by anybody. The seeds are scattered through the lot and how
many land in one sample rather than another is chance, so the allowance comes
from what chance can do rather than from how carefully the analyst worked.

That makes the shape of it fixed: the spread of a count goes with the square
root of the count, so the allowance widens slowly and never stops widening. It
is written here as a table for the small numbers, because that is what is
pinned above the bench, and as the curve the table was cut from once the counts
get big enough that a table would run off the page. The two have to meet
exactly where they hand over, and there is a test that says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "COUNT_BANDS",
    "TABLE_LIMIT",
    "SPREAD_FACTOR",
    "tolerance_for",
    "CountComparison",
    "compare",
]

#: Each entry is the highest total the row covers, and the allowance for it.
#: Read from the top down, first row whose total is not exceeded wins.
COUNT_BANDS: tuple[tuple[int, int], ...] = (
    (0, 0),
    (1, 2),
    (3, 3),
    (5, 4),
    (7, 5),
    (10, 6),
    (14, 7),
    (18, 8),
    (23, 9),
    (28, 10),
    (34, 11),
    (40, 12),
)

#: Above this total the table stops and the curve takes over.
TABLE_LIMIT = 40

#: Two counts of the same lot differ by chance alone, and this is how much of
#: that chance the station is willing to call agreement. It is the ordinary two
#: sided five percent figure applied to the square root of the total.
SPREAD_FACTOR = Decimal("1.96")


def tolerance_for(total: int) -> int:
    """The largest difference two counts adding to ``total`` may show.

    Both counts go in as their sum rather than separately. That is not a
    shortcut: the spread of the difference depends on how many seeds there
    were altogether, and splitting six as five and one or as three and three
    does not change what chance was working with.
    """
    if total < 0:
        raise ValueError("two counts cannot add up to less than nothing")

    if total <= TABLE_LIMIT:
        for up_to, allowance in COUNT_BANDS:
            if total <= up_to:
                return allowance

    spread = Decimal(total).sqrt() * SPREAD_FACTOR
    return int(spread.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class CountComparison:
    """Two counts, the allowance between them, and the verdict."""

    first: int
    second: int
    allowance: int

    @property
    def total(self) -> int:
        return self.first + self.second

    @property
    def difference(self) -> int:
        return abs(self.first - self.second)

    @property
    def within_tolerance(self) -> bool:
        return self.difference <= self.allowance

    def explain(self) -> str:
        """A sentence for the worksheet, whichever way it went."""
        verdict = "within" if self.within_tolerance else "outside"
        return (
            f"{self.first} against {self.second}, differing by {self.difference} "
            f"with {self.allowance} allowed, {verdict} tolerance"
        )


def compare(first: int, second: int) -> CountComparison:
    """Compares two counts of the same species in the same lot."""
    if first < 0 or second < 0:
        raise ValueError("a count cannot be negative")

    return CountComparison(
        first=first,
        second=second,
        allowance=tolerance_for(first + second),
    )
