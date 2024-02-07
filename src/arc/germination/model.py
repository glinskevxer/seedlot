"""The germination test: four hundred seeds, counted one at a time.

Four replicates of a hundred seeds go down on the substrate. At the end every
seed has been put into one of five categories, and the categories are not
opinions. A normal seedling has all the structures it needs to grow on; an
abnormal one has germinated but is missing or has damaged one of them; a hard
seed never took up water; a fresh seed took up water and did nothing; a dead
seed has gone soft.

The distinction that costs money is normal against abnormal, because only
normal seedlings count towards the germination percentage on the certificate.
The distinction that causes arguments is hard against fresh, because a hard
seed will often grow next year and a fresh one usually will not.

Every replicate has to account for all hundred seeds. A replicate whose
categories do not add up has been miscounted, and there is no way to tell which
category is wrong, so the whole replicate is void rather than adjusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from arc.errors import Rule

__all__ = [
    "Category",
    "REPLICATE_LAYOUTS",
    "Replicate",
    "GerminationTest",
    "check_test",
]


class Category(Enum):
    """What one seed turned out to be."""

    NORMAL = "normal seedling"
    ABNORMAL = "abnormal seedling"
    HARD = "hard seed"
    FRESH = "fresh ungerminated"
    DEAD = "dead"

    @property
    def label(self) -> str:
        return self.value

    @property
    def counts_as_germinated(self) -> bool:
        """Only a normal seedling does. This is the whole certificate."""
        return self is Category.NORMAL

    @property
    def may_still_grow(self) -> bool:
        """Hard seed usually does eventually. Fresh seed is a bad sign."""
        return self in (Category.HARD, Category.FRESH)


#: The layouts the handbook allows, as (replicates, seeds each). Four hundred
#: seeds either way; the smaller replicates are for seed too large to fit a
#: hundred on a tray.
REPLICATE_LAYOUTS: tuple[tuple[int, int], ...] = ((4, 100), (8, 50), (16, 25))


@dataclass(frozen=True)
class Replicate:
    """One tray, counted."""

    normal: int
    abnormal: int
    hard: int
    fresh: int
    dead: int

    def __post_init__(self) -> None:
        for name in ("normal", "abnormal", "hard", "fresh", "dead"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be a negative count")

    @property
    def seeds(self) -> int:
        """Every seed that was put down, which is what has to add up."""
        return self.normal + self.abnormal + self.hard + self.fresh + self.dead

    def count_of(self, category: Category) -> int:
        return {
            Category.NORMAL: self.normal,
            Category.ABNORMAL: self.abnormal,
            Category.HARD: self.hard,
            Category.FRESH: self.fresh,
            Category.DEAD: self.dead,
        }[category]

    def percentage_normal(self, seeds_expected: int) -> Decimal:
        """Normal seedlings as a percentage of the seeds that were put down."""
        if seeds_expected <= 0:
            raise ValueError("a replicate with no seeds in it is not a replicate")
        return (Decimal(self.normal) / Decimal(seeds_expected)) * Decimal(100)


@dataclass(frozen=True)
class GerminationTest:
    """One germination test, from setting down to final count."""

    lot_reference: str
    species_name: str
    replicates: tuple[Replicate, ...]
    seeds_per_replicate: int
    set_down_on: date
    final_count_on: date
    analyst: str
    is_retest: bool = False

    def __post_init__(self) -> None:
        if not self.replicates:
            raise ValueError("a germination test needs replicates")
        if self.final_count_on < self.set_down_on:
            raise ValueError("the final count cannot come before the test was set down")

    @property
    def layout(self) -> tuple[int, int]:
        return (len(self.replicates), self.seeds_per_replicate)

    @property
    def seeds_tested(self) -> int:
        return len(self.replicates) * self.seeds_per_replicate

    @property
    def days_taken(self) -> int:
        return (self.final_count_on - self.set_down_on).days

    def total_of(self, category: Category) -> int:
        return sum(replicate.count_of(category) for replicate in self.replicates)

    def percentages_normal(self) -> tuple[Decimal, ...]:
        return tuple(
            replicate.percentage_normal(self.seeds_per_replicate)
            for replicate in self.replicates
        )

    @property
    def mean_normal(self) -> int:
        """The germination percentage, rounded to a whole number as reported.

        The handbook reports germination as a whole number. Carrying a decimal
        here and rounding at the end would let 89.5 be reported as 90 in one
        place and 89 in another depending on which code path got there first.
        """
        total_normal = self.total_of(Category.NORMAL)
        percentage = (Decimal(total_normal) / Decimal(self.seeds_tested)) * Decimal(100)
        return int(percentage.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def replicate_range(self) -> Decimal:
        """The spread between the best replicate and the worst."""
        percentages = self.percentages_normal()
        return max(percentages) - min(percentages)


def check_test(test: GerminationTest) -> list[Rule]:
    """Whether the counting itself holds together, before any rule about seed."""
    broken: list[Rule] = []
    subject = test.lot_reference

    if test.layout not in REPLICATE_LAYOUTS:
        allowed = ", ".join(f"{count} of {size}" for count, size in REPLICATE_LAYOUTS)
        broken.append(
            Rule(
                "LAYOUT_NOT_ALLOWED",
                f"{test.layout[0]} replicates of {test.layout[1]} is not a layout the "
                f"handbook recognises, use {allowed}",
                subject,
            )
        )

    for index, replicate in enumerate(test.replicates, start=1):
        if replicate.seeds != test.seeds_per_replicate:
            broken.append(
                Rule(
                    "REPLICATE_DOES_NOT_ADD_UP",
                    f"replicate {index} accounts for {replicate.seeds} seeds and "
                    f"{test.seeds_per_replicate} were put down",
                    subject,
                )
            )

    return broken
