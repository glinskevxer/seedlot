"""Fixtures shared by the whole suite.

Real lots of real species, because a test written against a made up species
proves the code works against a species nobody sends in.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from arc.lots.model import ContainerKind, LotReference, SeedLot
from arc.species import register
from arc.species.model import Species


@pytest.fixture
def wheat() -> Species:
    """Thirty tonne maximum, one kilogram submitted sample, not chaffy."""
    return register.require("Triticum aestivum")


@pytest.fixture
def ryegrass() -> Species:
    """Ten tonne maximum, sixty gram sample, chaffy and prechilled."""
    return register.require("Lolium perenne")


@pytest.fixture
def rape() -> Species:
    """Small seeded, oily, and goes in the low oven."""
    return register.require("Brassica napus")


def make_lot(
    *,
    serial: int = 41,
    species_name: str = "Triticum aestivum",
    weight_kg: str = "24000",
    container_kind: ContainerKind = ContainerKind.BAG,
    container_count: int = 480,
    year: int = 2024,
) -> SeedLot:
    return SeedLot(
        reference=LotReference(year=year, serial=serial),
        species_name=species_name,
        declared_weight_kg=Decimal(weight_kg),
        container_kind=container_kind,
        container_count=container_count,
        merchant="Ravenscar Grain",
        sealed_on=date(year, 9, 12),
        origin_country="GB",
    )


@pytest.fixture
def wheat_lot() -> SeedLot:
    """Twenty four tonnes in 480 fifty kilogram bags. Comfortably legal."""
    return make_lot()


@pytest.fixture
def grass_lot() -> SeedLot:
    """Eight tonnes of ryegrass in twenty five kilogram bags."""
    return make_lot(
        serial=77,
        species_name="Lolium perenne",
        weight_kg="8000",
        container_count=320,
    )
