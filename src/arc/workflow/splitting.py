"""Splitting a consignment that is too heavy to be one lot.

A merchant sends forty tonnes of wheat. The maximum lot weight for wheat is
thirty, and that limit is not administrative: above it a sample drawn from the
lot stops being representative of all of it, so a certificate on forty tonnes
would be a claim the sampling cannot support.

The consignment is therefore split into sublots, each inside the maximum, and
each is a lot in its own right from then on. It is sampled, tested and
certified separately, and its certificate carries its own weight.

The consignment itself is recorded too, closed, so the sublots have something
to point at. It is not a lot anybody can test, which is exactly what closed
means, and without it the station has three references on the shelf and nothing
saying they arrived on the same lorry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_DOWN, Decimal

from arc.errors import Rule, RuleBroken
from arc.lots.model import LotReference, LotStatus, SeedLot
from arc.lots.rules import sublots_needed
from arc.species import register
from arc.storage.lots import LotRepository

__all__ = ["Split", "plan_split", "split"]


@dataclass(frozen=True)
class Split:
    """A consignment and the lots it became."""

    consignment: SeedLot
    sublots: tuple[SeedLot, ...]

    @property
    def count(self) -> int:
        return len(self.sublots)

    def describe(self) -> str:
        weights = ", ".join(str(lot.declared_weight_kg) for lot in self.sublots)
        return f"{self.consignment.reference} split into {self.count} lots of {weights} kg"


def plan_split(consignment: SeedLot, *, starting_serial: int) -> Split:
    """Works out the sublots without writing anything.

    The weights are not simply divided. Dividing forty tonnes by two gives two
    of twenty and that is fine, but dividing by three gives a repeating decimal
    and three lots that do not add up to what arrived. So every sublot but the
    last is rounded down to the kilogram and the last one carries whatever is
    left, which is the only arrangement where the parts sum to the whole.
    """
    species = register.require(consignment.species_name)
    needed = sublots_needed(consignment, species)

    if needed <= 1:
        raise RuleBroken(
            [
                Rule(
                    "CONSIGNMENT_NEEDS_NO_SPLIT",
                    f"{consignment.declared_weight_kg} kg of {species.common_name} is "
                    f"inside the {species.max_lot_kg} kg maximum",
                    str(consignment.reference),
                )
            ]
        )

    each = (consignment.declared_weight_kg / needed).quantize(Decimal("1"), rounding=ROUND_DOWN)
    containers = consignment.container_count // needed

    sublots: list[SeedLot] = []
    for index in range(needed):
        last = index == needed - 1
        weight = consignment.declared_weight_kg - each * (needed - 1) if last else each
        count = consignment.container_count - containers * (needed - 1) if last else containers
        sublots.append(
            replace(
                consignment,
                reference=LotReference(
                    year=consignment.reference.year,
                    serial=starting_serial + index,
                ),
                declared_weight_kg=weight,
                container_count=count,
                species_name=species.botanical_name,
                sublot_of=consignment.reference,
            )
        )

    return Split(consignment=consignment, sublots=tuple(sublots))


def split(
    consignment: SeedLot,
    lots: LotRepository,
    *,
    starting_serial: int,
    on: date,
) -> Split:
    """Records the consignment closed and books its sublots in."""
    planned = plan_split(consignment, starting_serial=starting_serial)

    if lots.find(consignment.reference) is not None:
        raise RuleBroken(
            [
                Rule(
                    "LOT_ALREADY_BOOKED_IN",
                    f"{consignment.reference} was booked in already",
                    str(consignment.reference),
                )
            ]
        )

    for sublot in planned.sublots:
        if lots.find(sublot.reference) is not None:
            raise RuleBroken(
                [
                    Rule(
                        "SUBLOT_REFERENCE_TAKEN",
                        f"{sublot.reference} is already in use, so the sublots "
                        "cannot be numbered from there",
                        str(sublot.reference),
                    )
                ]
            )

    closed = replace(
        consignment,
        species_name=register.require(consignment.species_name).botanical_name,
        notes="consignment, split into sublots",
    )
    closed.move_to(LotStatus.CLOSED)
    lots.save(closed, booked_in_on=on)

    for sublot in planned.sublots:
        lots.save(sublot, booked_in_on=on)

    return planned
