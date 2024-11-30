"""Seed that has not germinated and is not dead.

A germination test answers one question: how many of these seeds produce a
normal seedling under the conditions in the handbook. Seed that ends the test
still firm has not answered it. It might be dormant and perfectly good, or it
might be about to die in a store, and the two look identical on the tray.

So the station does not report a low germination on a dormant sample. It
applies whichever treatment the handbook gives for the species, runs the test
again, and reports that. The rules here decide when that is required, which
treatment is allowed, and what has to be said afterwards.

Hard seed and fresh seed are different things and are treated differently. Hard
seed is a legume with a coat water cannot get through. It is real seed, it is
reported as its own figure, and a buyer can act on it. Fresh ungerminated seed
took up water and then did nothing, and above a few percent it means the test
has not finished rather than that the lot is poor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from arc.errors import Rule
from arc.germination.model import Category, GerminationTest
from arc.species.model import SeedClass, Species

__all__ = [
    "Treatment",
    "FRESH_SEED_LIMIT",
    "HARD_SEED_REPORTED_FROM",
    "Dormancy",
    "treatments_for",
    "assess",
    "check_treatment",
]


class Treatment(Enum):
    """What was done to the sample to get it out of dormancy.

    Every one of these changes the conditions the seeds were under, so every
    one of them has to be named on the certificate. A germination of 94 after
    a gibberellic acid soak is not the same claim as a germination of 94.
    """

    NONE = "none"
    PRECHILL = "prechill"
    PREHEAT = "preheat"
    KNO3 = "potassium nitrate"
    GIBBERELLIC_ACID = "gibberellic acid"
    SCARIFY = "scarify"

    @property
    def was_applied(self) -> bool:
        return self is not Treatment.NONE

    @property
    def goes_on_the_certificate(self) -> bool:
        """Anything that was done to the seed has to be declared."""
        return self.was_applied

    @property
    def label(self) -> str:
        return self.value


#: Fresh ungerminated seed above this share of the test means the test has not
#: finished. Below it, a few seeds that never got going are ordinary.
FRESH_SEED_LIMIT = 5

#: Hard seed at or above this share is reported as its own figure rather than
#: folded into the seeds that failed.
HARD_SEED_REPORTED_FROM = 1

#: Which treatments the handbook allows for which kind of seed. A cereal that
#: will not come up gets a prechill or a nitrate soak; a legume with a coat
#: water cannot cross gets scarified, and nothing else will help it.
_BY_CLASS: dict[SeedClass, tuple[Treatment, ...]] = {
    SeedClass.CEREAL: (Treatment.PRECHILL, Treatment.PREHEAT, Treatment.KNO3),
    SeedClass.GRASS: (Treatment.PRECHILL, Treatment.KNO3, Treatment.GIBBERELLIC_ACID),
    SeedClass.LARGE_LEGUME: (Treatment.SCARIFY,),
    SeedClass.SMALL_LEGUME: (Treatment.SCARIFY, Treatment.PRECHILL),
    SeedClass.BRASSICA: (Treatment.PRECHILL, Treatment.KNO3),
    SeedClass.OIL_AND_FIBRE: (Treatment.PRECHILL, Treatment.KNO3),
    SeedClass.VEGETABLE: (Treatment.PRECHILL,),
    SeedClass.BEET: (Treatment.PRECHILL,),
}


def treatments_for(species: Species) -> tuple[Treatment, ...]:
    """Every treatment the handbook allows on this species, none included.

    None is always allowed, and is first, because most samples need nothing
    and an analyst reading the list should see that before anything else.
    """
    return (Treatment.NONE, *_BY_CLASS.get(species.seed_class, ()))


@dataclass(frozen=True)
class Dormancy:
    """What a finished test says about seed that did not germinate."""

    fresh_percent: int
    hard_percent: int
    normal_percent: int

    @property
    def is_dormant(self) -> bool:
        """Whether enough seed is sitting there for the test to be unfinished."""
        return self.fresh_percent > FRESH_SEED_LIMIT

    @property
    def hard_seed_is_reportable(self) -> bool:
        return self.hard_percent >= HARD_SEED_REPORTED_FROM

    @property
    def could_still_reach(self) -> int:
        """The best the lot could do if every dormant seed came good.

        Not a figure that goes anywhere near a certificate. It is what the
        analyst looks at to decide whether a retest is worth the fortnight.
        """
        return self.normal_percent + self.fresh_percent + self.hard_percent

    def explain(self) -> str:
        if not self.is_dormant:
            return f"{self.fresh_percent} percent fresh, within the ordinary few"
        return (
            f"{self.fresh_percent} percent fresh ungerminated against a limit of "
            f"{FRESH_SEED_LIMIT}, so the test has not finished"
        )


def assess(test: GerminationTest) -> Dormancy:
    """Reads dormancy off a finished test."""
    seeds = test.seeds_tested
    if seeds == 0:
        raise ValueError("a test with no seeds in it says nothing about dormancy")

    def share(category: Category) -> int:
        return round(test.total_of(category) * 100 / seeds)

    return Dormancy(
        fresh_percent=share(Category.FRESH),
        hard_percent=share(Category.HARD),
        normal_percent=test.mean_normal,
    )


def check_treatment(
    test: GerminationTest,
    treatment: Treatment,
    species: Species,
) -> list[Rule]:
    """Whether this test, with this treatment, may be reported.

    The two directions both matter. A dormant sample tested with no treatment
    is a result nobody may quote, and a treated sample is a different claim
    that has to be declared even when the treatment was the right one.
    """
    broken: list[Rule] = []
    subject = test.lot_reference
    dormancy = assess(test)

    if treatment not in treatments_for(species):
        broken.append(
            Rule(
                "TREATMENT_NOT_ALLOWED",
                f"{treatment.value} is not a treatment the handbook gives for "
                f"{species.common_name}",
                subject,
            )
        )

    if dormancy.is_dormant and not treatment.was_applied and not test.is_retest:
        broken.append(
            Rule(
                "DORMANCY_NOT_BROKEN",
                f"{dormancy.explain()}, so treat the sample and test it again "
                "rather than reporting this",
                subject,
            )
        )

    if dormancy.is_dormant and treatment.was_applied and not test.is_retest:
        # The treatment was applied to the first test rather than to a repeat.
        # That is allowed, and it is still a different test from the plain one,
        # so it has to be marked as what it is.
        broken.append(
            Rule(
                "TREATED_TEST_NOT_MARKED",
                f"this test had {treatment.value} applied, so it is a retest "
                "and has to be recorded as one",
                subject,
            )
        )

    return broken
