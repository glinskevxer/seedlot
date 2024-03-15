"""Booking a lot in, which is where every job at the station starts.

The work is small and the order it is done in is the whole of it. The species
has to be known before the lot can be checked, because the maximum lot weight
is a species number. The lot has to pass before a sampling plan means anything.
And the plan has to exist before the sampler is sent out, because a sampler who
comes back with the wrong amount has wasted a trip to a warehouse.

Nothing here writes a lot that failed its checks. A rejected lot is a
conversation with the merchant, not a row in the database with a flag on it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from arc.errors import RuleBroken
from arc.lots.model import SeedLot
from arc.lots.rules import check_lot, sublots_needed
from arc.sampling.plan import SamplingPlan, plan_for
from arc.species import register
from arc.species.model import Species
from arc.storage.lots import LotRepository

__all__ = ["BookedIn", "book_in", "split_advice"]


@dataclass(frozen=True)
class BookedIn:
    """A lot that was accepted, and the docket that goes with it."""

    lot: SeedLot
    species: Species
    plan: SamplingPlan

    @property
    def reference(self) -> str:
        return str(self.lot.reference)


def book_in(
    lot: SeedLot,
    lots: LotRepository,
    *,
    on: date,
) -> BookedIn:
    """Accepts a lot and works out how it is to be sampled.

    The species is looked up from what was written on the paperwork, which is
    why an unknown species fails here rather than three steps later when
    somebody asks for a working sample size.
    """
    species = register.require(lot.species_name)

    # Whatever was written on the paperwork, the lot is stored under the
    # botanical name. Everything downstream looks lots up by species, and a
    # station holding the same species under "wheat" and "Triticum aestivum"
    # answers "which lots of this are open" wrongly and quietly.
    accepted = replace(lot, species_name=species.botanical_name)

    broken = check_lot(accepted, species)
    if broken:
        raise RuleBroken(broken)

    plan = plan_for(accepted, species)
    lots.save(accepted, booked_in_on=on)

    return BookedIn(lot=accepted, species=species, plan=plan)


def split_advice(lot: SeedLot) -> tuple[int, str]:
    """How many sublots an over weight lot needs, and what to tell the merchant.

    Called after a refusal, so that the person on the phone has an answer
    rather than only a rejection.
    """
    species = register.require(lot.species_name)
    needed = sublots_needed(lot, species)

    if needed == 1:
        return 1, f"{lot.reference} is inside the maximum and needs no splitting"

    each = lot.declared_weight_kg / needed
    return needed, (
        f"{lot.reference} is over the {species.max_lot_kg} kg maximum for "
        f"{species.common_name}, split it into {needed} sublots of about "
        f"{each.quantize(lot.declared_weight_kg)} kg and book each in separately"
    )
