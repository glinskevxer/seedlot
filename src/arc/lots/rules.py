"""Whether a lot may be tested at all, and what has to happen first.

The maximum lot weight is the rule with teeth. A lot over it cannot be sampled
representatively, so nothing taken from it means anything, and the station
either refuses the work or splits the lot into sublots that are each inside the
limit.

The five percent tolerance on top is the part people get wrong. It is not
slack in the maximum: it is an allowance for a declared weight being an
estimate. A lot four percent over is tested as one lot and the certificate says
nothing about it. A lot six percent over is split, and the sublots each get
their own reference, their own sampling and their own certificate.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from arc.errors import Rule
from arc.lots.model import ContainerKind, SeedLot
from arc.species.model import Species

__all__ = [
    "WEIGHT_TOLERANCE",
    "MAX_BAG_KG",
    "check_lot",
    "over_maximum_by",
    "sublots_needed",
    "must_be_sampled_in_stream",
]

#: How far over the maximum a declared weight may be before the lot is split.
WEIGHT_TOLERANCE = Decimal("0.05")

#: A container heavier than this cannot be sampled with a spear, whatever it
#: is called on the paperwork.
MAX_BAG_KG = Decimal("100")


def over_maximum_by(lot: SeedLot, species: Species) -> Decimal:
    """How far over the maximum the lot is, as a fraction. Zero when inside it."""
    maximum = Decimal(species.max_lot_kg)
    if lot.declared_weight_kg <= maximum:
        return Decimal(0)
    return (lot.declared_weight_kg - maximum) / maximum


def sublots_needed(lot: SeedLot, species: Species) -> int:
    """How many sublots the lot has to be split into.

    One means no split. The tolerance is applied first, so a lot inside it is
    one sublot however close to the line it sits.
    """
    if over_maximum_by(lot, species) <= WEIGHT_TOLERANCE:
        return 1
    maximum = Decimal(species.max_lot_kg)
    return int((lot.declared_weight_kg / maximum).to_integral_value(rounding=ROUND_CEILING))


def must_be_sampled_in_stream(lot: SeedLot) -> bool:
    """True when the seed has to be moving for the sample to be representative.

    Bulk and big bags always. Ordinary bags too, once they are heavy enough
    that a spear cannot reach the middle, which is the case the container kind
    on the paperwork will not tell you about.
    """
    if lot.container_kind.must_be_sampled_in_stream:
        return True
    average = lot.average_container_kg
    return average is not None and average > MAX_BAG_KG


def check_lot(lot: SeedLot, species: Species) -> list[Rule]:
    """Everything wrong with the lot, all of it, before any of it is worked on."""
    broken: list[Rule] = []
    subject = str(lot.reference)

    excess = over_maximum_by(lot, species)
    if excess > WEIGHT_TOLERANCE:
        needed = sublots_needed(lot, species)
        broken.append(
            Rule(
                "LOT_OVER_MAXIMUM",
                f"{lot.declared_weight_kg} kg is over the {species.max_lot_kg} kg maximum "
                f"for {species.common_name} by more than the five percent allowance, "
                f"so it has to be split into {needed} sublots",
                subject,
            )
        )
    elif excess > 0:
        # Inside the allowance. Worth recording on the worksheet and worth not
        # refusing, which is the whole point of the allowance existing.
        pass

    if lot.container_kind is ContainerKind.BAG:
        average = lot.average_container_kg
        if average is not None and average > MAX_BAG_KG:
            broken.append(
                Rule(
                    "BAGS_TOO_HEAVY",
                    f"bags averaging {average.quantize(Decimal('0.1'))} kg cannot be "
                    "spear sampled, sample the lot in stream instead",
                    subject,
                )
            )

    if lot.container_kind.is_containerised and lot.container_count > 0:
        average = lot.average_container_kg
        if average is not None and average < Decimal("1"):
            broken.append(
                Rule(
                    "CONTAINER_COUNT_IMPLAUSIBLE",
                    f"{lot.container_count} containers holding "
                    f"{lot.declared_weight_kg} kg works out under a kilogram each, "
                    "check the declaration",
                    subject,
                )
            )

    return broken
