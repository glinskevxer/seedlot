"""Comparing this station's result with another laboratory's.

A merchant who does not like a result sends the same lot somewhere else, and
the two stations disagree. That is expected: two laboratories working from two
submitted samples of the same lot have every source of variation that two
analysts in one room have, plus the sampling itself.

So the allowance between laboratories is wider than the allowance between two
analyses on one bench, and it is wider again than the spread allowed inside a
single test. Three tables, same numbers, keyed differently, and using the wrong
one either starts an argument that should not have happened or ends one that
should have.

The rule the station cares about is what follows a disagreement. Two results
inside the allowance are both right and the earlier one stands. Two outside it
mean somebody has made a mistake, and neither station can tell which from the
numbers alone, so the lot goes to a third laboratory.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from arc.germination.outcome import between_tests_tolerance
from arc.purity.tolerance import tolerance_for as purity_within_lab

__all__ = [
    "GERMINATION_BETWEEN_LABS",
    "germination_allowance",
    "purity_allowance",
    "RefereeVerdict",
    "Referee",
    "compare_germination",
    "compare_purity",
]

#: Table 5D, folded around fifty like the others. Read top down on the folded
#: mean of the two laboratories' results.
GERMINATION_BETWEEN_LABS: tuple[tuple[int, int], ...] = (
    (45, 11),
    (34, 10),
    (28, 9),
    (23, 8),
    (16, 7),
    (10, 6),
    (6, 5),
    (3, 4),
    (1, 3),
    (0, 2),
)

#: How much wider a purity comparison is between laboratories than within one.
#: The handbook prints a separate table; the ratio it works out to is steady
#: enough across the bands that it is applied rather than transcribed twice.
PURITY_BETWEEN_LAB_FACTOR = Decimal("1.4")


def germination_allowance(mean_percent: int) -> int:
    """How far two laboratories' germinations may differ."""
    if not 0 <= mean_percent <= 100:
        raise ValueError(f"a germination percentage runs from 0 to 100, not {mean_percent}")
    folded = min(mean_percent, 100 - mean_percent)
    for floor, allowance in GERMINATION_BETWEEN_LABS:
        if folded >= floor:
            return allowance
    raise AssertionError("the last band starts at zero and must have matched")


def purity_allowance(average: Decimal, *, chaffy: bool) -> Decimal:
    """How far two laboratories' purity analyses may differ."""
    within = purity_within_lab(average, chaffy=chaffy)
    return (within * PURITY_BETWEEN_LAB_FACTOR).quantize(Decimal("0.01"))


class RefereeVerdict(Enum):
    """What follows a comparison with another laboratory."""

    AGREE = "the two agree, the first result stands"
    REFER = "the two do not agree, refer the lot to a third laboratory"

    @property
    def needs_a_third_opinion(self) -> bool:
        return self is RefereeVerdict.REFER


@dataclass(frozen=True)
class Referee:
    """Two laboratories' results, held up against each other."""

    ours: Decimal
    theirs: Decimal
    allowance: Decimal
    verdict: RefereeVerdict

    @property
    def difference(self) -> Decimal:
        return abs(self.ours - self.theirs)

    def explain(self) -> str:
        return (
            f"we reported {self.ours} and they reported {self.theirs}, "
            f"{self.difference} apart against the {self.allowance} allowed between "
            f"laboratories: {self.verdict.value}"
        )


def compare_germination(ours: int, theirs: int) -> Referee:
    """Whether two laboratories' germination results can both be right."""
    mean = (ours + theirs) // 2
    allowance = germination_allowance(mean)
    difference = abs(ours - theirs)

    return Referee(
        ours=Decimal(ours),
        theirs=Decimal(theirs),
        allowance=Decimal(allowance),
        verdict=RefereeVerdict.AGREE
        if difference <= allowance
        else RefereeVerdict.REFER,
    )


def compare_purity(ours: Decimal, theirs: Decimal, *, chaffy: bool) -> Referee:
    """Whether two laboratories' purity analyses can both be right."""
    average = (ours + theirs) / 2
    allowance = purity_allowance(average, chaffy=chaffy)
    difference = abs(ours - theirs)

    return Referee(
        ours=ours,
        theirs=theirs,
        allowance=allowance,
        verdict=RefereeVerdict.AGREE
        if difference <= allowance
        else RefereeVerdict.REFER,
    )


def widens_correctly(mean_percent: int) -> bool:
    """That the three germination allowances stand in the right order.

    Inside one test the four trays may spread most, because a hundred seeds is
    a small sample. Between two whole tests on one bench the allowance is
    tightest. Between laboratories it opens up again, because the sampling is
    no longer shared. Used by the suite to hold that shape.
    """
    from arc.germination.tolerance import maximum_range_for

    within_one_test = maximum_range_for(mean_percent)
    between_tests = between_tests_tolerance(mean_percent)
    between_labs = germination_allowance(mean_percent)

    return between_tests <= between_labs <= within_one_test
