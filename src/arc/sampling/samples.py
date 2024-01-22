"""The chain of samples, and the fact that each one is drawn from the last.

Spearfuls make a composite. The composite is reduced to the submitted sample,
which is what actually arrives at the station in a sealed bag. The submitted
sample is reduced again into working samples, one for each determination, and
those are what get analysed.

Every step down that chain loses seed, and every step has to lose it evenly.
The whole apparatus of dividers and halving exists for that one reason, and the
reason a method is allowed for one species and not another is that some seed
does not flow. Chaffy seed poured into a set of cups does not distribute, it
bridges, and the sample that comes out is the light fraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from arc.errors import Rule
from arc.species.model import Species

__all__ = [
    "ReductionMethod",
    "Determination",
    "SubmittedSample",
    "WorkingSample",
    "methods_allowed_for",
    "check_submitted_sample",
    "working_sample_weight_for",
]


class ReductionMethod(Enum):
    """How a sample is halved down without picking favourites."""

    MECHANICAL_DIVIDER = "mechanical divider"
    MODIFIED_HALVING = "modified halving"
    RANDOM_CUPS = "random cups"
    SPOON = "spoon"

    @property
    def needs_free_flowing_seed(self) -> bool:
        """True for the methods that only work if the seed pours.

        Chaffy seed bridges in a cup and packs in a spoon, so what comes out is
        the light fraction rather than a share of the sample.
        """
        return self in (ReductionMethod.RANDOM_CUPS, ReductionMethod.SPOON)


class Determination(Enum):
    """What a working sample is drawn for.

    Each takes a different amount, and the amounts are not proportional to each
    other: counting other species needs ten times the purity sample because the
    contaminant it is looking for might be one seed in ten thousand.
    """

    PURITY = "purity"
    OTHER_SEEDS = "other seed count"
    MOISTURE = "moisture"
    THOUSAND_SEED_WEIGHT = "thousand seed weight"
    GERMINATION = "germination"


def methods_allowed_for(species: Species) -> tuple[ReductionMethod, ...]:
    """The reduction methods this species may be put through."""
    if species.chaffy:
        return (ReductionMethod.MECHANICAL_DIVIDER, ReductionMethod.MODIFIED_HALVING)
    return tuple(ReductionMethod)


@dataclass(frozen=True)
class SubmittedSample:
    """What arrived at the station, in the bag, with the seal on it."""

    lot_reference: str
    species_name: str
    weight_g: Decimal
    received_on: date
    seal_intact: bool
    reduction_method: ReductionMethod
    sampler: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.weight_g <= 0:
            raise ValueError("an empty bag is not a sample")


@dataclass(frozen=True)
class WorkingSample:
    """What was actually weighed out onto the bench for one determination."""

    submitted_from: str
    determination: Determination
    weight_g: Decimal
    reduction_method: ReductionMethod

    def __post_init__(self) -> None:
        if self.weight_g <= 0:
            raise ValueError("an empty working sample is not a sample")


def working_sample_weight_for(species: Species, determination: Determination) -> Decimal:
    """How much seed the determination needs.

    Germination is counted rather than weighed, so it has no weight here and
    asking for one is a mistake worth catching loudly.
    """
    match determination:
        case Determination.PURITY:
            return species.purity_working_sample_g
        case Determination.OTHER_SEEDS:
            return species.other_seed_working_sample_g
        case Determination.MOISTURE:
            # Enough for two determinations plus what the grinder keeps.
            return Decimal("50") if species.moisture.grinding.is_required else Decimal("15")
        case Determination.THOUSAND_SEED_WEIGHT:
            # Eight hundred seeds, taken from the pure seed fraction rather
            # than weighed off the submitted sample.
            return Decimal("0")
        case Determination.GERMINATION:
            raise ValueError("a germination test is counted out, not weighed out")
    raise AssertionError("every determination is handled above")


def check_submitted_sample(sample: SubmittedSample, species: Species) -> list[Rule]:
    """Whether the bag on the bench can be worked on at all."""
    broken: list[Rule] = []
    subject = sample.lot_reference

    if not sample.seal_intact:
        broken.append(
            Rule(
                "SEAL_BROKEN",
                "the seal was not intact on arrival, so the sample cannot be "
                "certified as drawn from the lot",
                subject,
            )
        )

    if sample.weight_g < species.submitted_sample_g:
        short_by = species.submitted_sample_g - sample.weight_g
        broken.append(
            Rule(
                "SAMPLE_UNDER_WEIGHT",
                f"{sample.weight_g} g is {short_by} g short of the "
                f"{species.submitted_sample_g} g needed for {species.common_name}",
                subject,
            )
        )

    if sample.reduction_method not in methods_allowed_for(species):
        broken.append(
            Rule(
                "REDUCTION_METHOD_NOT_ALLOWED",
                f"{species.common_name} is chaffy and cannot be reduced by "
                f"{sample.reduction_method.value}, use a divider or halving",
                subject,
            )
        )

    return broken
