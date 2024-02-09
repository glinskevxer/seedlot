"""How far four replicates of the same sample may disagree.

Four trays of a hundred seeds from one bag will not give the same count. The
handbook says how much spread is normal, and anything wider than that means the
sample was not mixed, the trays were not treated alike, or somebody counted an
abnormal seedling as a normal one on one tray and not on another.

The allowance depends on the germination itself. A sample germinating at 99 has
almost nowhere to vary and is allowed a range of 5. One germinating at 55 has
room to move in both directions and is allowed 20. And because a sample at 95
is the same problem as one at 5 seen from the other end, the table folds around
fifty exactly the way the purity one does.

Getting this wrong in the tight direction fails honest work and costs a fortnight
while the test is redone. Getting it wrong in the loose direction certifies a
germination the seed does not have, which is worse.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "RangeBand",
    "REPLICATE_RANGES",
    "maximum_range_for",
    "RangeCheck",
    "check_range",
]


@dataclass(frozen=True)
class RangeBand:
    """One row, written on the low side of fifty.

    ``at_least`` is inclusive and the bands are read from the top down, so the
    first band the folded mean reaches is the one that applies.
    """

    at_least: int
    maximum_range: int


#: Table 5B, folded. A mean of 96 and a mean of 4 get the same allowance.
REPLICATE_RANGES: tuple[RangeBand, ...] = (
    RangeBand(at_least=45, maximum_range=20),
    RangeBand(at_least=34, maximum_range=19),
    RangeBand(at_least=28, maximum_range=18),
    RangeBand(at_least=23, maximum_range=17),
    RangeBand(at_least=20, maximum_range=16),
    RangeBand(at_least=17, maximum_range=15),
    RangeBand(at_least=14, maximum_range=14),
    RangeBand(at_least=12, maximum_range=13),
    RangeBand(at_least=10, maximum_range=12),
    RangeBand(at_least=8, maximum_range=11),
    RangeBand(at_least=6, maximum_range=10),
    RangeBand(at_least=5, maximum_range=9),
    RangeBand(at_least=4, maximum_range=8),
    RangeBand(at_least=3, maximum_range=7),
    RangeBand(at_least=2, maximum_range=6),
    RangeBand(at_least=0, maximum_range=5),
)


def fold(mean_percent: int) -> int:
    """A sample at 96 varies like one at 4. Look both up the same way."""
    if not 0 <= mean_percent <= 100:
        raise ValueError(f"a germination percentage runs from 0 to 100, not {mean_percent}")
    return min(mean_percent, 100 - mean_percent)


def maximum_range_for(mean_percent: int) -> int:
    """The widest spread four replicates at this mean are allowed."""
    folded = fold(mean_percent)
    for band in REPLICATE_RANGES:
        if folded >= band.at_least:
            return band.maximum_range
    raise AssertionError("the last band starts at zero and must have matched")


@dataclass(frozen=True)
class RangeCheck:
    """Four replicates held up against the table."""

    mean_percent: int
    observed_range: Decimal
    maximum_range: int

    @property
    def within_tolerance(self) -> bool:
        return self.observed_range <= Decimal(self.maximum_range)

    @property
    def must_be_repeated(self) -> bool:
        """The only thing to be done with a test that spread too far."""
        return not self.within_tolerance

    def explain(self) -> str:
        verdict = "within" if self.within_tolerance else "outside"
        return (
            f"the replicates span {self.observed_range} at a mean of "
            f"{self.mean_percent} percent, {verdict} the {self.maximum_range} allowed"
        )


def check_range(mean_percent: int, observed_range: Decimal) -> RangeCheck:
    """Whether a test's spread is acceptable at the germination it reported."""
    return RangeCheck(
        mean_percent=mean_percent,
        observed_range=observed_range,
        maximum_range=maximum_range_for(mean_percent),
    )
