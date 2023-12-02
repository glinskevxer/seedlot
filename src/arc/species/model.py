"""What the station needs to know about a species before it can test it.

Every number here comes out of the testing handbook and none of them are
negotiable at the bench. They are kept together because they are read together:
deciding how to test a sample of red fescue means knowing the maximum lot
weight, the submitted sample size, the working sample size, whether the seed is
chaffy, which substrate the germination goes on, and which oven the moisture
sample sees. Splitting them across modules only means six lookups instead of
one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

__all__ = [
    "SeedClass",
    "Substrate",
    "OvenMethod",
    "Grinding",
    "GerminationMethod",
    "MoistureMethod",
    "Species",
]


class SeedClass(Enum):
    """Broad groupings the handbook uses when it does not name a species.

    Tolerance tables and working sample rules fall back on the class when a
    species is not listed individually, so this is not decoration.
    """

    CEREAL = "cereal"
    LARGE_LEGUME = "large legume"
    SMALL_LEGUME = "small legume"
    GRASS = "grass"
    BRASSICA = "brassica"
    VEGETABLE = "vegetable"
    BEET = "beet"
    OIL_AND_FIBRE = "oil and fibre"

    @property
    def label(self) -> str:
        return self.value


class Substrate(Enum):
    """What the seeds are germinated on."""

    TOP_OF_PAPER = "TP"
    BETWEEN_PAPER = "BP"
    PLEATED_PAPER = "PP"
    SAND = "S"
    ON_SAND = "TS"

    @property
    def code(self) -> str:
        return self.value


class OvenMethod(Enum):
    """Which oven programme a moisture sample goes through.

    Oily seed cannot go in the hot oven: the oil oxidises and the sample gains
    weight, which reads as moisture that was never there.
    """

    LOW_CONSTANT = "103C/17h"
    HIGH_CONSTANT_1H = "130C/1h"
    HIGH_CONSTANT_2H = "130C/2h"
    HIGH_CONSTANT_4H = "130C/4h"

    @property
    def celsius(self) -> int:
        return 103 if self is OvenMethod.LOW_CONSTANT else 130

    @property
    def hours(self) -> Decimal:
        return Decimal({"103C/17h": 17, "130C/1h": 1, "130C/2h": 2, "130C/4h": 4}[self.value])

    @property
    def is_low_constant(self) -> bool:
        return self is OvenMethod.LOW_CONSTANT


class Grinding(Enum):
    """How finely the moisture sample is ground before it goes in."""

    NONE = "whole"
    COARSE = "coarse"
    FINE = "fine"

    @property
    def is_required(self) -> bool:
        return self is not Grinding.NONE


@dataclass(frozen=True)
class GerminationMethod:
    """How a germination test on this species is set up and read.

    ``first_count_day`` is when the normal seedlings that are ready get counted
    and removed; ``final_count_day`` ends the test. A count taken on any other
    day is not a result, which is why both are here rather than left to whoever
    is on the bench that week.
    """

    substrate: Substrate
    temperature: str
    first_count_day: int
    final_count_day: int
    prechill_days: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.first_count_day < 1:
            raise ValueError("the first count cannot be before the first day")
        if self.final_count_day < self.first_count_day:
            raise ValueError("the final count cannot come before the first count")
        if self.prechill_days < 0:
            raise ValueError("a prechill cannot be negative")

    @property
    def duration_days(self) -> int:
        """Days from setting the test down to reading it, prechill included."""
        return self.prechill_days + self.final_count_day

    @property
    def needs_prechill(self) -> bool:
        return self.prechill_days > 0


@dataclass(frozen=True)
class MoistureMethod:
    """How a moisture determination on this species is done."""

    oven: OvenMethod
    grinding: Grinding
    predry_required: bool = False

    @property
    def is_two_stage(self) -> bool:
        """Wet seed is dried once before grinding, then properly. Two weighings."""
        return self.predry_required


@dataclass(frozen=True)
class Species:
    """One species as the station knows it."""

    botanical_name: str
    common_name: str
    seed_class: SeedClass
    max_lot_kg: int
    submitted_sample_g: Decimal
    purity_working_sample_g: Decimal
    chaffy: bool
    germination: GerminationMethod
    moisture: MoistureMethod
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_lot_kg <= 0:
            raise ValueError(f"{self.botanical_name} needs a positive maximum lot weight")
        if self.submitted_sample_g <= 0:
            raise ValueError(f"{self.botanical_name} needs a positive submitted sample")
        if self.purity_working_sample_g > self.submitted_sample_g:
            raise ValueError(
                f"{self.botanical_name} cannot take a working sample larger than "
                "the sample it is taken from"
            )

    @property
    def key(self) -> str:
        """The lookup key: the botanical name, lower cased."""
        return self.botanical_name.lower()

    @property
    def other_seed_working_sample_g(self) -> Decimal:
        """Counting other species needs ten times the purity working sample."""
        return self.purity_working_sample_g * Decimal(10)

    def names(self) -> tuple[str, ...]:
        """Everything this species answers to, lower cased."""
        return tuple(
            name.lower()
            for name in (self.botanical_name, self.common_name, *self.aliases)
        )

    def __str__(self) -> str:
        return f"{self.botanical_name} ({self.common_name})"
