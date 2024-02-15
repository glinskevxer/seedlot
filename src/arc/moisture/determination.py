"""Moisture content: three weighings and a decision about a fourth.

The container is weighed empty, weighed with the sample in it, put in the oven,
and weighed again. What came off is water, and what is left is dry matter. The
percentage is worked against the original wet weight, because that is what the
seed is sold by.

Wet seed cannot go straight in. Above about seventeen percent the sample cannot
be ground without smearing, and grinding is what lets the water out of the
middle of a cereal grain. So a wet sample is dried once at low heat to get it
grindable, ground, and then determined properly, and the two stages are
combined. The combination is not addition: the second stage measures what is
left after the first, so the product term comes back off.

Whether the second stage is needed is decided by the first stage result, which
means the procedure is chosen by a number the procedure itself produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from arc.errors import Rule
from arc.species.model import Species

__all__ = [
    "PREDRY_THRESHOLD",
    "DUPLICATE_TOLERANCE",
    "Weighing",
    "MoistureResult",
    "moisture_of",
    "combine_stages",
    "needs_predrying",
    "check_duplicates",
]

#: Above this the sample is predried before it is ground.
PREDRY_THRESHOLD = Decimal("17.0")

#: Two determinations of one sample may differ by this much and no more.
DUPLICATE_TOLERANCE = Decimal("0.2")


@dataclass(frozen=True)
class Weighing:
    """One container through the oven, weighed three times."""

    container_g: Decimal
    with_sample_g: Decimal
    after_drying_g: Decimal

    def __post_init__(self) -> None:
        if self.with_sample_g <= self.container_g:
            raise ValueError("the container weighed no more with the sample in it")
        if self.after_drying_g > self.with_sample_g:
            raise ValueError("the sample came out of the oven heavier than it went in")
        if self.after_drying_g < self.container_g:
            raise ValueError("the sample weighed less than its own container")

    @property
    def wet_sample_g(self) -> Decimal:
        return self.with_sample_g - self.container_g

    @property
    def water_lost_g(self) -> Decimal:
        return self.with_sample_g - self.after_drying_g

    @property
    def dry_sample_g(self) -> Decimal:
        return self.after_drying_g - self.container_g


@dataclass(frozen=True)
class MoistureResult:
    """One determination, reported to a tenth of a percent."""

    percent: Decimal
    wet_sample_g: Decimal
    water_lost_g: Decimal

    @property
    def is_wet(self) -> bool:
        """True when the sample has to be predried before it can be ground."""
        return self.percent > PREDRY_THRESHOLD


def moisture_of(weighing: Weighing) -> MoistureResult:
    """The moisture content of one container, against the wet weight."""
    percent = (weighing.water_lost_g / weighing.wet_sample_g) * Decimal(100)
    return MoistureResult(
        percent=percent.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        wet_sample_g=weighing.wet_sample_g,
        water_lost_g=weighing.water_lost_g,
    )


def needs_predrying(first_stage: MoistureResult, species: Species) -> bool:
    """Whether a second stage is required.

    Seed that is not ground at all does not need predrying however wet it is,
    because there is nothing to smear. That is why the species comes into a
    decision that otherwise looks like it is only about the number.
    """
    if not species.moisture.grinding.is_required:
        return False
    return first_stage.is_wet


def combine_stages(predry_percent: Decimal, second_percent: Decimal) -> Decimal:
    """Puts a predried sample's two stages back together.

    The second stage is measured on what the first stage left behind, so adding
    the two would count the same water twice over the part they share.
    """
    for value in (predry_percent, second_percent):
        if value < 0 or value > 100:
            raise ValueError(f"a moisture content runs from 0 to 100, not {value}")

    combined = (
        predry_percent
        + second_percent
        - (predry_percent * second_percent / Decimal(100))
    )
    return combined.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def check_duplicates(first: MoistureResult, second: MoistureResult) -> list[Rule]:
    """Whether two determinations of one sample are close enough to stand."""
    apart = abs(first.percent - second.percent)
    if apart <= DUPLICATE_TOLERANCE:
        return []
    return [
        Rule(
            "MOISTURE_DUPLICATES_DISAGREE",
            f"{first.percent} and {second.percent} differ by {apart}, over the "
            f"{DUPLICATE_TOLERANCE} allowed, so both determinations are done again",
        )
    ]
