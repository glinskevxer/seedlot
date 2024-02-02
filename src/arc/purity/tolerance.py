"""Whether two purity analyses of the same sample agree.

Two analysts pushing the same sample into piles will not get the same answer,
and the handbook says how far apart they are allowed to be before one of them
is wrong. The allowance is not a flat figure. It depends on two things and the
dependence is the whole point of the table.

It depends on how big the component is, because being a tenth of a percent out
on a component that is half the sample is nothing and being a tenth out on one
that is a tenth of a percent is a doubling. And because a component at 99.8 is
the same problem as one at 0.2 seen from the other end, one row of the table
covers both: the lookup folds the average onto the low side before it starts.

It depends on whether the seed is chaffy, because chaffy seed is harder to
separate and two honest analysts will differ by more on it. That column is
roughly half again as wide, and using the wrong one either fails work that was
fine or passes work that was not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "ToleranceBand",
    "PURITY_TOLERANCES",
    "tolerance_for",
    "Comparison",
    "compare",
]


@dataclass(frozen=True)
class ToleranceBand:
    """One row of the table, written on the low side of fifty.

    ``up_to`` is inclusive. A band is chosen by the folded average falling on
    or under it, reading the table from the top down.
    """

    up_to: Decimal
    non_chaffy: Decimal
    chaffy: Decimal

    def allowance(self, *, chaffy: bool) -> Decimal:
        return self.chaffy if chaffy else self.non_chaffy


def _band(up_to: str, non_chaffy: str, chaffy: str) -> ToleranceBand:
    return ToleranceBand(Decimal(up_to), Decimal(non_chaffy), Decimal(chaffy))


#: Table 3B, folded. Read top down: the first band the folded average is at or
#: under is the one that applies.
PURITY_TOLERANCES: tuple[ToleranceBand, ...] = (
    _band("0.04", "0.20", "0.23"),
    _band("0.09", "0.23", "0.34"),
    _band("0.14", "0.26", "0.38"),
    _band("0.19", "0.29", "0.43"),
    _band("0.24", "0.32", "0.47"),
    _band("0.29", "0.34", "0.50"),
    _band("0.39", "0.36", "0.53"),
    _band("0.49", "0.40", "0.59"),
    _band("0.59", "0.43", "0.65"),
    _band("0.69", "0.47", "0.69"),
    _band("0.79", "0.50", "0.74"),
    _band("0.99", "0.54", "0.76"),
    _band("1.24", "0.59", "0.89"),
    _band("1.49", "0.65", "0.95"),
    _band("1.99", "0.72", "1.06"),
    _band("2.49", "0.81", "1.15"),
    _band("2.99", "0.88", "1.20"),
    _band("3.99", "0.99", "1.32"),
    _band("4.99", "1.11", "1.50"),
    _band("5.99", "1.20", "1.65"),
    _band("6.99", "1.28", "1.76"),
    _band("7.99", "1.36", "1.86"),
    _band("8.99", "1.43", "1.95"),
    _band("9.99", "1.49", "2.04"),
    _band("14.99", "1.63", "2.23"),
    _band("19.99", "1.86", "2.55"),
    _band("24.99", "2.03", "2.78"),
    _band("29.99", "2.16", "2.96"),
    _band("34.99", "2.27", "3.10"),
    _band("39.99", "2.35", "3.21"),
    _band("44.99", "2.40", "3.28"),
    _band("50.00", "2.43", "3.31"),
)


def fold(average: Decimal) -> Decimal:
    """A component at 99.8 is the same problem as one at 0.2. Fold it over."""
    if average < 0 or average > 100:
        raise ValueError(f"a percentage runs from 0 to 100, not {average}")
    return min(average, Decimal(100) - average)


def tolerance_for(average: Decimal, *, chaffy: bool) -> Decimal:
    """How far two analyses of a component this size may be apart."""
    folded = fold(average)
    for band in PURITY_TOLERANCES:
        if folded <= band.up_to:
            return band.allowance(chaffy=chaffy)
    raise AssertionError("the last band reaches fifty and a folded average cannot exceed it")


@dataclass(frozen=True)
class Comparison:
    """Two analyses held up against each other."""

    first: Decimal
    second: Decimal
    tolerance: Decimal
    chaffy: bool

    @property
    def average(self) -> Decimal:
        return (self.first + self.second) / 2

    @property
    def difference(self) -> Decimal:
        return abs(self.first - self.second)

    @property
    def compatible(self) -> bool:
        """True when the two are close enough to be the same sample."""
        return self.difference <= self.tolerance

    def explain(self) -> str:
        verdict = "within" if self.compatible else "outside"
        seed = "chaffy" if self.chaffy else "free flowing"
        return (
            f"{self.first} and {self.second} differ by {self.difference}, "
            f"{verdict} the {self.tolerance} allowed for {seed} seed "
            f"averaging {self.average}"
        )


def compare(first: Decimal, second: Decimal, *, chaffy: bool) -> Comparison:
    """Whether two analyses of the same component agree.

    The tolerance is looked up on the average of the two, so which row of the
    table applies is decided by the numbers being compared rather than by
    anything known beforehand.
    """
    average = (first + second) / 2
    return Comparison(
        first=first,
        second=second,
        tolerance=tolerance_for(average, chaffy=chaffy),
        chaffy=chaffy,
    )
