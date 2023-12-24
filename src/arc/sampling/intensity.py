"""How many primary samples a lot needs, and where they come from.

A primary sample is one spearful. The number of them is the whole basis of the
claim that the submitted sample represents thirty tonnes of wheat, so it is the
one number nobody at the station is allowed to round down.

Which table applies depends on how the lot is put up, and that decision is made
elsewhere: a lot in ordinary bags is sampled by container, and everything else
is sampled as it moves. The two tables do not agree with each other and are not
meant to. Sampling twenty bags is a different problem from sampling a stream
that took an hour to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

__all__ = [
    "CONTAINER_BANDS",
    "STREAM_BANDS",
    "ContainerBand",
    "StreamBand",
    "primary_samples_for_containers",
    "primary_samples_for_stream",
    "containers_to_open",
]


@dataclass(frozen=True)
class ContainerBand:
    """One row of the container table.

    ``per_container`` and ``total`` are alternatives, not both. A small lot is
    sampled so many times per container; a large one gets a flat total spread
    across the lot, because thirty spearfuls out of four hundred bags is
    representative and four hundred spearfuls is a day's work for nothing.
    """

    up_to_containers: int | None
    per_container: int | None = None
    total: int | None = None
    minimum_total: int = 0

    def __post_init__(self) -> None:
        if (self.per_container is None) == (self.total is None):
            raise ValueError("a band is either per container or a flat total, not both")


@dataclass(frozen=True)
class StreamBand:
    """One row of the stream table: a spearful every so many kilograms."""

    up_to_kg: Decimal | None
    one_per_kg: Decimal | None
    minimum_total: int


#: Read top down, first band whose ceiling the count is under or on.
CONTAINER_BANDS: tuple[ContainerBand, ...] = (
    ContainerBand(up_to_containers=4, per_container=3, minimum_total=5),
    ContainerBand(up_to_containers=8, per_container=2, minimum_total=5),
    ContainerBand(up_to_containers=15, per_container=1, minimum_total=5),
    ContainerBand(up_to_containers=30, total=15),
    ContainerBand(up_to_containers=59, total=20),
    ContainerBand(up_to_containers=None, total=30),
)

STREAM_BANDS: tuple[StreamBand, ...] = (
    StreamBand(up_to_kg=Decimal("500"), one_per_kg=None, minimum_total=5),
    StreamBand(up_to_kg=Decimal("3000"), one_per_kg=Decimal("300"), minimum_total=5),
    StreamBand(up_to_kg=Decimal("20000"), one_per_kg=Decimal("500"), minimum_total=10),
    StreamBand(up_to_kg=None, one_per_kg=Decimal("700"), minimum_total=40),
)


def primary_samples_for_containers(container_count: int) -> int:
    """How many spearfuls a containerised lot needs."""
    if container_count < 1:
        raise ValueError("a containerised lot has at least one container")

    for band in CONTAINER_BANDS:
        if band.up_to_containers is None or container_count <= band.up_to_containers:
            if band.per_container is not None:
                taken = container_count * band.per_container
            else:
                assert band.total is not None
                taken = band.total
            return max(taken, band.minimum_total)

    raise AssertionError("the last container band has no ceiling and must have matched")


def primary_samples_for_stream(weight_kg: Decimal) -> int:
    """How many spearfuls a lot sampled in motion needs.

    The minimum is not a floor on the arithmetic, it is a separate rule. A four
    hundred kilogram lot gets five spearfuls even though the rate for its band
    would give it none at all.
    """
    if weight_kg <= 0:
        raise ValueError("a lot with no seed in it cannot be sampled")

    for band in STREAM_BANDS:
        if band.up_to_kg is None or weight_kg <= band.up_to_kg:
            if band.one_per_kg is None:
                return band.minimum_total
            by_rate = (weight_kg / band.one_per_kg).to_integral_value(rounding=ROUND_CEILING)
            return max(int(by_rate), band.minimum_total)

    raise AssertionError("the last stream band has no ceiling and must have matched")


def containers_to_open(container_count: int, primary_samples: int) -> int:
    """How many containers have to be opened to take that many spearfuls.

    On the flat total bands the spearfuls are spread out, so fewer containers
    are opened than exist. The handbook asks for at least every second one, and
    that floor is what this returns when the arithmetic would give less.
    """
    if container_count < 1:
        raise ValueError("a containerised lot has at least one container")

    if primary_samples >= container_count:
        return container_count

    every_second = -(-container_count // 2)
    return min(container_count, max(primary_samples, every_second))
