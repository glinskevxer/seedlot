"""Separating a working sample into what it is made of.

The analyst tips the working sample onto the board and pushes it into three
piles: pure seed of the species on the label, seed of anything else, and inert
matter, which is everything that is not a seed. Each pile is weighed and the
three weights become three percentages.

Two rules matter and both are about weighing rather than sorting.

The first is that the three piles have to add back up to what went on the
board. Seed gets lost: it goes on the floor, it stays in the tray, it blows
off. A small loss is expected and is absorbed by working the percentages from
the recovered total rather than the original. A loss over five percent means
something went badly wrong and the analysis is done again.

The second is that all three piles are weighed to the same precision, chosen
from the weight of the original working sample. Weighing the pure seed to whole
grams and the inert matter to milligrams produces percentages that cannot be
compared with anybody else's.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from arc.errors import Rule
from arc.quantities import Percentage, as_percentages, decimals_for, normalise_to_hundred, weigh
from arc.species.model import Species

__all__ = [
    "Component",
    "MAX_LOSS",
    "PurityAnalysis",
    "PurityResult",
    "analyse",
]

#: How much of the working sample may go missing before the analysis is void.
MAX_LOSS = Decimal("0.05")


class Component(Enum):
    """The three piles, in the order they are reported."""

    PURE_SEED = "pure seed"
    OTHER_SEED = "other seed"
    INERT_MATTER = "inert matter"

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class PurityAnalysis:
    """What the analyst weighed off the board."""

    working_sample_g: Decimal
    pure_seed_g: Decimal
    other_seed_g: Decimal
    inert_matter_g: Decimal
    analyst: str

    def __post_init__(self) -> None:
        if self.working_sample_g <= 0:
            raise ValueError("nothing was put on the board")
        for name in ("pure_seed_g", "other_seed_g", "inert_matter_g"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def recovered_g(self) -> Decimal:
        """What came back off the board, which is rarely what went on it."""
        return self.pure_seed_g + self.other_seed_g + self.inert_matter_g

    @property
    def loss_g(self) -> Decimal:
        return self.working_sample_g - self.recovered_g

    @property
    def loss_fraction(self) -> Decimal:
        """How much went missing, as a fraction. Negative if the piles gained."""
        return self.loss_g / self.working_sample_g

    def weights(self) -> tuple[Decimal, Decimal, Decimal]:
        return (self.pure_seed_g, self.other_seed_g, self.inert_matter_g)


@dataclass(frozen=True)
class PurityResult:
    """The analysis as it will be reported."""

    pure_seed: Percentage
    other_seed: Percentage
    inert_matter: Percentage
    weighed_to_places: int
    loss_fraction: Decimal

    def as_dict(self) -> dict[Component, Percentage]:
        return {
            Component.PURE_SEED: self.pure_seed,
            Component.OTHER_SEED: self.other_seed,
            Component.INERT_MATTER: self.inert_matter,
        }

    def percentage_of(self, component: Component) -> Percentage:
        return self.as_dict()[component]

    @property
    def sums_to_hundred(self) -> bool:
        return (
            self.pure_seed.value + self.other_seed.value + self.inert_matter.value
            == Decimal("100.0")
        )


def check_analysis(analysis: PurityAnalysis, species: Species) -> list[Rule]:
    """Whether the weighing can be turned into a result."""
    broken: list[Rule] = []

    if abs(analysis.loss_fraction) > MAX_LOSS:
        percent = (analysis.loss_fraction * 100).quantize(Decimal("0.1"))
        broken.append(
            Rule(
                "PURITY_LOSS_TOO_HIGH",
                f"the three fractions differ from the working sample by {percent} percent, "
                "which is over the five percent allowance, so the analysis is void",
                species.botanical_name,
            )
        )

    if analysis.working_sample_g < species.purity_working_sample_g:
        broken.append(
            Rule(
                "PURITY_SAMPLE_UNDER_WEIGHT",
                f"{analysis.working_sample_g} g is under the "
                f"{species.purity_working_sample_g} g working sample "
                f"{species.common_name} needs",
                species.botanical_name,
            )
        )

    return broken


def analyse(analysis: PurityAnalysis, species: Species) -> PurityResult:
    """Turns three weights into three percentages that add up.

    The percentages are worked from the recovered weight rather than from what
    went on the board. Using the original would spread the loss across the
    components in proportion, which quietly reports seed that was never found.
    """
    from arc.errors import RuleBroken

    broken = check_analysis(analysis, species)
    if broken:
        raise RuleBroken(broken)

    places = decimals_for(analysis.working_sample_g)
    weighed = [weigh(part, places=places) for part in analysis.weights()]
    recovered = sum(weighed, Decimal(0))

    pure, other, inert = normalise_to_hundred(as_percentages(weighed, recovered))

    return PurityResult(
        pure_seed=pure,
        other_seed=other,
        inert_matter=inert,
        weighed_to_places=places,
        loss_fraction=analysis.loss_fraction,
    )
