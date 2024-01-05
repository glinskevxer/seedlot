"""Turning a lot into an instruction the sampler can carry out.

The sampler is standing in a warehouse with a spear and a bag. What they need
is a number of spearfuls, a number of containers to open, and a minimum weight
to come back with. Working that out means reading the lot, the species and both
intensity tables, and the answer is different for two lots of the same weight
that happen to be put up differently.

The plan is a value, not a procedure. It is worked out once at booking in,
printed on the sampling docket, and kept, because a sample taken to yesterday's
plan is still valid and a plan recomputed after the fact proves nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arc.errors import RuleBroken
from arc.lots.model import SeedLot
from arc.lots.rules import check_lot, must_be_sampled_in_stream
from arc.sampling.intensity import (
    containers_to_open,
    primary_samples_for_containers,
    primary_samples_for_stream,
)
from arc.species.model import Species

__all__ = ["SamplingRoute", "SamplingPlan", "plan_for"]


class SamplingRoute:
    """Which of the two tables the plan was worked out from."""

    BY_CONTAINER = "by container"
    IN_STREAM = "in stream"


@dataclass(frozen=True)
class SamplingPlan:
    """What the sampler is told to do, and why."""

    lot_reference: str
    species_name: str
    route: str
    primary_samples: int
    containers_to_open: int | None
    minimum_submitted_g: Decimal

    @property
    def is_in_stream(self) -> bool:
        return self.route == SamplingRoute.IN_STREAM

    def docket_lines(self) -> tuple[str, ...]:
        """The plan as it is printed on the sampling docket."""
        lines = [
            f"Lot {self.lot_reference}",
            f"Species {self.species_name}",
            f"Sample {self.route}",
            f"Take {self.primary_samples} primary samples",
        ]
        if self.containers_to_open is not None:
            lines.append(f"Open at least {self.containers_to_open} containers")
        lines.append(f"Submit at least {self.minimum_submitted_g} g")
        return tuple(lines)


def plan_for(lot: SeedLot, species: Species) -> SamplingPlan:
    """The sampling plan for a lot, or a refusal saying why there is not one.

    The lot is checked first. There is no point telling somebody how to sample
    a lot that is twice the maximum weight: the instruction would be carried
    out and the result would still mean nothing.
    """
    broken = check_lot(lot, species)
    if broken:
        raise RuleBroken(broken)

    if must_be_sampled_in_stream(lot):
        route = SamplingRoute.IN_STREAM
        primary = primary_samples_for_stream(lot.declared_weight_kg)
        containers = None
    else:
        route = SamplingRoute.BY_CONTAINER
        primary = primary_samples_for_containers(lot.container_count)
        containers = containers_to_open(lot.container_count, primary)

    return SamplingPlan(
        lot_reference=str(lot.reference),
        species_name=species.botanical_name,
        route=route,
        primary_samples=primary,
        containers_to_open=containers,
        minimum_submitted_g=species.submitted_sample_g,
    )
