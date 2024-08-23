"""Thousand seed weight: eight hundred seeds, weighed in eight lots.

The figure a farmer actually uses. Seed is bought by weight and sown by seeds
per square metre, so the thousand seed weight is what turns one into the other,
and getting it wrong by ten percent means a crop drilled ten percent too thin.

It is measured by counting eight replicates of a hundred seeds out of the pure
seed fraction and weighing each. The mean of the eight, times ten, is the
thousand seed weight. The eight are not there for precision in the ordinary
sense: they are there so that the coefficient of variation can be calculated,
and the coefficient of variation is what says whether the counting was any good.

The limit on it depends on the seed. Chaffy seed varies more between individual
seeds no matter how carefully it is counted, so it is allowed half again as
much scatter before the determination is thrown out.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from arc.errors import Rule
from arc.species.model import Species

__all__ = [
    "REPLICATES",
    "SEEDS_PER_REPLICATE",
    "CV_LIMIT_FREE_FLOWING",
    "CV_LIMIT_CHAFFY",
    "ThousandSeedWeight",
    "cv_limit_for",
    "measure",
]

REPLICATES = 8
SEEDS_PER_REPLICATE = 100

#: How much scatter is tolerated between the eight replicates.
CV_LIMIT_FREE_FLOWING = Decimal("4.0")
CV_LIMIT_CHAFFY = Decimal("6.0")


def cv_limit_for(species: Species) -> Decimal:
    """The scatter this species is allowed between replicates."""
    return CV_LIMIT_CHAFFY if species.chaffy else CV_LIMIT_FREE_FLOWING


@dataclass(frozen=True)
class ThousandSeedWeight:
    """The determination, with the working shown."""

    replicate_weights_g: tuple[Decimal, ...]
    mean_g: Decimal
    standard_deviation_g: Decimal
    coefficient_of_variation: Decimal
    limit: Decimal

    @property
    def grams_per_thousand(self) -> Decimal:
        """The figure the certificate carries, to one decimal place."""
        return (self.mean_g * Decimal(10)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def within_tolerance(self) -> bool:
        return self.coefficient_of_variation <= self.limit

    def explain(self) -> str:
        verdict = "within" if self.within_tolerance else "outside"
        return (
            f"the eight replicates vary by {self.coefficient_of_variation} percent, "
            f"{verdict} the {self.limit} allowed"
        )


def measure(weights_g: tuple[Decimal, ...], species: Species) -> ThousandSeedWeight:
    """Works the thousand seed weight out of eight replicate weighings.

    The standard deviation is the sample one, dividing by seven rather than
    eight, because the eight replicates are a sample of the lot and not the
    whole of it.
    """
    if len(weights_g) != REPLICATES:
        raise ValueError(f"a thousand seed weight needs {REPLICATES} replicates")
    if any(weight <= 0 for weight in weights_g):
        raise ValueError("a replicate of a hundred seeds cannot weigh nothing")

    count = Decimal(len(weights_g))
    mean = sum(weights_g, Decimal(0)) / count

    squared_error = sum(((weight - mean) ** 2 for weight in weights_g), Decimal(0))
    variance = squared_error / (count - 1)
    deviation = variance.sqrt()

    cv = (deviation / mean * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    return ThousandSeedWeight(
        replicate_weights_g=weights_g,
        mean_g=mean,
        standard_deviation_g=deviation,
        coefficient_of_variation=cv,
        limit=cv_limit_for(species),
    )


def check(determination: ThousandSeedWeight, species: Species) -> list[Rule]:
    """Whether the determination may be reported."""
    if determination.within_tolerance:
        return []
    return [
        Rule(
            "TSW_SCATTER_TOO_WIDE",
            f"{determination.explain()}, so the eight replicates are counted again",
            species.botanical_name,
        )
    ]
