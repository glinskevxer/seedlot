"""The seed lot: the thing a certificate is about.

A lot is a quantity of seed that has been mixed and is being treated as one
uniform thing. Everything the station does afterwards rests on that assumption,
so the rules about how big a lot may be and how it is put up are not
bookkeeping. A lot over the maximum weight cannot be sampled representatively,
and a result taken from an unrepresentative sample describes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

__all__ = ["ContainerKind", "LotReference", "LotStatus", "SeedLot"]

_REFERENCE = re.compile(r"^L-(?P<year>\d{4})-(?P<serial>\d{4})$")


@dataclass(frozen=True, order=True)
class LotReference:
    """The station's own reference for a lot, in the form L-2024-0041.

    Parsed rather than kept as a string because the year is read constantly:
    the certificate carries it, the archive is filed by it, and the retest
    rules count from it.
    """

    year: int
    serial: int

    def __post_init__(self) -> None:
        if not 2000 <= self.year <= 2099:
            raise ValueError(f"{self.year} is not a year this station has worked")
        if not 1 <= self.serial <= 9999:
            raise ValueError("a lot serial runs from 1 to 9999")

    @classmethod
    def parse(cls, text: str) -> LotReference:
        match = _REFERENCE.match(text.strip().upper())
        if match is None:
            raise ValueError(f"{text!r} is not a lot reference, expected L-2024-0041")
        return cls(year=int(match.group("year")), serial=int(match.group("serial")))

    def __str__(self) -> str:
        return f"L-{self.year:04d}-{self.serial:04d}"


class ContainerKind(Enum):
    """How the lot is put up, which decides how it can be sampled.

    The distinction that matters is whether a sampling spear can reach the
    middle of a container. It cannot reach the middle of a big bag, so those
    are sampled as they are filled or emptied rather than in the warehouse.
    """

    BAG = "bag"
    BIG_BAG = "big bag"
    BULK = "bulk"

    @property
    def is_containerised(self) -> bool:
        return self is not ContainerKind.BULK

    @property
    def must_be_sampled_in_stream(self) -> bool:
        """True when a spear cannot reach the middle and the seed must be moving."""
        return self is not ContainerKind.BAG


class LotStatus(Enum):
    """Where the lot is in its life at the station."""

    BOOKED_IN = "booked in"
    SAMPLED = "sampled"
    IN_TEST = "in test"
    REPORTED = "reported"
    CLOSED = "closed"

    @property
    def is_open(self) -> bool:
        return self not in (LotStatus.REPORTED, LotStatus.CLOSED)

    def can_move_to(self, nxt: LotStatus) -> bool:
        allowed: dict[LotStatus, tuple[LotStatus, ...]] = {
            LotStatus.BOOKED_IN: (LotStatus.SAMPLED, LotStatus.CLOSED),
            LotStatus.SAMPLED: (LotStatus.IN_TEST, LotStatus.CLOSED),
            LotStatus.IN_TEST: (LotStatus.REPORTED, LotStatus.CLOSED),
            LotStatus.REPORTED: (LotStatus.CLOSED,),
            LotStatus.CLOSED: (),
        }
        return nxt in allowed[self]


@dataclass
class SeedLot:
    """One lot as it was declared when it came in.

    The weight and the container count are what the merchant declared, not what
    the station measured. Nobody weighs thirty tonnes of wheat to check, so the
    declaration is what the rules are applied to and the certificate says so.
    """

    reference: LotReference
    species_name: str
    declared_weight_kg: Decimal
    container_kind: ContainerKind
    container_count: int
    merchant: str
    sealed_on: date
    origin_country: str
    status: LotStatus = LotStatus.BOOKED_IN
    notes: str = ""
    sublot_of: LotReference | None = field(default=None)

    def __post_init__(self) -> None:
        if self.declared_weight_kg <= 0:
            raise ValueError("a lot with no seed in it is not a lot")
        if self.container_kind.is_containerised and self.container_count < 1:
            raise ValueError("a containerised lot needs at least one container")
        if not self.container_kind.is_containerised and self.container_count != 0:
            raise ValueError("a bulk lot has no containers to count")
        if len(self.origin_country) != 2:
            raise ValueError("the country of origin is a two letter code")

    @property
    def is_sublot(self) -> bool:
        """True when this came out of splitting something that was over weight."""
        return self.sublot_of is not None

    @property
    def average_container_kg(self) -> Decimal | None:
        """What one container holds on average, or nothing for a bulk lot."""
        if not self.container_kind.is_containerised:
            return None
        return self.declared_weight_kg / Decimal(self.container_count)

    def move_to(self, nxt: LotStatus) -> None:
        if not self.status.can_move_to(nxt):
            raise ValueError(f"a lot cannot go from {self.status.value} to {nxt.value}")
        self.status = nxt

    def __str__(self) -> str:
        return f"{self.reference} {self.species_name} {self.declared_weight_kg} kg"
