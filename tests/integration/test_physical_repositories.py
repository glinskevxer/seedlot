"""Moisture and thousand seed weight, round tripped."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from arc.moisture.determination import Weighing, combine_stages, moisture_of
from arc.species import register
from arc.storage.lots import LotRepository
from arc.storage.physical import (
    MoistureRepository,
    MoistureStage,
    SeedWeightRepository,
)
from arc.storage.schema import connect, migrate
from arc.weight.thousand_seed import measure
from tests.conftest import make_lot
from tests.support import open_test_database

BOOKED = date(2024, 9, 18)
DETERMINED = date(2024, 9, 25)


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def moisture(db) -> MoistureRepository:
    return MoistureRepository(db)


@pytest.fixture
def seed_weight(db) -> SeedWeightRepository:
    return SeedWeightRepository(db)


def weighing(container="12.000", wet="22.000", dry="20.600") -> Weighing:
    return Weighing(
        container_g=Decimal(container),
        with_sample_g=Decimal(wet),
        after_drying_g=Decimal(dry),
    )


TIDY = tuple(
    Decimal(value)
    for value in ("4.51", "4.48", "4.52", "4.49", "4.50", "4.53", "4.47", "4.50")
)


class TestMoisture:
    def test_a_determination_comes_back_as_it_went_in(self, moisture) -> None:
        result = moisture_of(weighing())

        moisture.record(
            "L-2024-0041", weighing(), result, analyst="J. W.", determined_on=DETERMINED
        )
        stored = moisture.for_lot("L-2024-0041")

        assert len(stored) == 1
        assert stored[0].result.percent == Decimal("14.0")
        assert stored[0].weighing.wet_sample_g == Decimal("10.000")
        assert stored[0].determined_on == DETERMINED

    def test_the_weights_keep_the_precision_they_were_weighed_to(self, moisture) -> None:
        moisture.record(
            "L-2024-0041",
            weighing(),
            moisture_of(weighing()),
            analyst="J. W.",
            determined_on=DETERMINED,
        )

        assert str(moisture.for_lot("L-2024-0041")[0].weighing.container_g) == "12.000"

    def test_a_single_stage_determination_is_what_gets_reported(self, moisture) -> None:
        moisture.record(
            "L-2024-0041",
            weighing(),
            moisture_of(weighing()),
            analyst="J. W.",
            determined_on=DETERMINED,
        )

        assert moisture.reportable_for_lot("L-2024-0041") == Decimal("14.0")

    def test_a_lot_with_nothing_determined_reports_nothing(self, moisture) -> None:
        assert moisture.reportable_for_lot("L-2024-0041") is None
        assert moisture.for_lot("L-2024-0041") == ()

    def test_a_two_stage_determination_reports_the_combination(self, moisture) -> None:
        predry = moisture_of(weighing(dry="21.500"))
        second = moisture_of(weighing(dry="20.600"))
        combined = combine_stages(predry.percent, second.percent)

        moisture.record(
            "L-2024-0041", weighing(dry="21.500"), predry,
            analyst="J. W.", determined_on=DETERMINED, stage=MoistureStage.PREDRY,
        )
        moisture.record(
            "L-2024-0041", weighing(dry="20.600"), second,
            analyst="J. W.", determined_on=DETERMINED, stage=MoistureStage.SECOND,
            combined_percent=combined,
        )

        assert moisture.reportable_for_lot("L-2024-0041") == combined

    def test_a_second_stage_on_its_own_is_never_reported_as_the_moisture(
        self, moisture
    ) -> None:
        # A second stage row with no combination on it is arithmetic in
        # progress, and reporting it would understate a wet sample badly.
        moisture.record(
            "L-2024-0041", weighing(dry="21.500"), moisture_of(weighing(dry="21.500")),
            analyst="J. W.", determined_on=DETERMINED, stage=MoistureStage.PREDRY,
        )
        moisture.record(
            "L-2024-0041", weighing(dry="20.600"), moisture_of(weighing(dry="20.600")),
            analyst="J. W.", determined_on=DETERMINED, stage=MoistureStage.SECOND,
        )

        assert moisture.reportable_for_lot("L-2024-0041") == Decimal("5.0")

    def test_only_the_single_stage_is_a_result_on_its_own(self) -> None:
        assert not MoistureStage.SINGLE.is_part_of_a_pair
        assert MoistureStage.PREDRY.is_part_of_a_pair
        assert MoistureStage.SECOND.is_part_of_a_pair

    def test_a_determination_of_a_lot_that_does_not_exist_is_refused(
        self, moisture
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            moisture.record(
                "L-2024-9999",
                weighing(),
                moisture_of(weighing()),
                analyst="J. W.",
                determined_on=DETERMINED,
            )


class TestSeedWeight:
    def test_a_determination_comes_back_with_its_eight_replicates(
        self, seed_weight
    ) -> None:
        wheat = register.require("wheat")

        seed_weight.record(
            "L-2024-0041", measure(TIDY, wheat), analyst="J. W.", determined_on=DETERMINED
        )
        stored = seed_weight.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert len(stored.replicate_weights_g) == 8
        assert stored.replicate_weights_g[0] == Decimal("4.51")

    def test_the_figure_the_certificate_carries_survives(self, seed_weight) -> None:
        wheat = register.require("wheat")
        original = measure(TIDY, wheat)

        seed_weight.record(
            "L-2024-0041", original, analyst="J. W.", determined_on=DETERMINED
        )
        stored = seed_weight.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert stored.grams_per_thousand == original.grams_per_thousand

    def test_the_scatter_and_the_limit_that_was_applied_are_both_kept(
        self, seed_weight
    ) -> None:
        # Which limit was used is part of the record: the same numbers pass on
        # grass and fail on wheat, and an audit asks which was applied.
        grass = register.require("perennial ryegrass")

        seed_weight.record(
            "L-2024-0041", measure(TIDY, grass), analyst="J. W.", determined_on=DETERMINED
        )
        stored = seed_weight.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert stored.limit == Decimal("6.0")
        assert stored.within_tolerance

    def test_a_second_determination_does_not_replace_the_first(self, seed_weight) -> None:
        wheat = register.require("wheat")
        heavier = tuple(weight + Decimal("0.10") for weight in TIDY)

        seed_weight.record(
            "L-2024-0041", measure(TIDY, wheat), analyst="J. W.", determined_on=DETERMINED
        )
        seed_weight.record(
            "L-2024-0041", measure(heavier, wheat), analyst="J. W.", determined_on=DETERMINED
        )

        assert len(seed_weight.for_lot("L-2024-0041")) == 2

    def test_a_lot_with_nothing_determined_has_nothing(self, seed_weight) -> None:
        assert seed_weight.for_lot("L-2024-0041") == ()
        assert seed_weight.latest_for_lot("L-2024-0041") is None

    def test_a_determination_of_a_lot_that_does_not_exist_leaves_no_replicates(
        self, seed_weight, db
    ) -> None:
        wheat = register.require("wheat")

        with pytest.raises(sqlite3.IntegrityError):
            seed_weight.record(
                "L-2024-9999", measure(TIDY, wheat), analyst="J. W.", determined_on=DETERMINED
            )

        assert db.execute("select count(*) from seed_weight_replicate").fetchone()[0] == 0
