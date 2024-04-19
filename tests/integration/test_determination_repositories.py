"""Determinations, round tripped through the database."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from arc.germination.model import GerminationTest, Replicate
from arc.purity.analysis import PurityAnalysis, analyse
from arc.species import register
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.schema import connect, migrate
from tests.conftest import make_lot

BOOKED = date(2024, 9, 18)


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "arc.sqlite3")
    migrate(connection)
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def purity(db) -> PurityRepository:
    return PurityRepository(db)


@pytest.fixture
def germination(db) -> GerminationRepository:
    return GerminationRepository(db)


def an_analysis(pure: str = "118.2") -> PurityAnalysis:
    return PurityAnalysis(
        working_sample_g=Decimal("120.0"),
        pure_seed_g=Decimal(pure),
        other_seed_g=Decimal("0.9"),
        inert_matter_g=Decimal("0.9"),
        analyst="J. Whitfield",
    )


def a_test(*normals: int, is_retest: bool = False) -> GerminationTest:
    return GerminationTest(
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        replicates=tuple(
            Replicate(normal=n, abnormal=100 - n, hard=0, fresh=0, dead=0) for n in normals
        ),
        seeds_per_replicate=100,
        set_down_on=date(2024, 9, 20),
        final_count_on=date(2024, 9, 28),
        analyst="J. Whitfield",
        is_retest=is_retest,
    )


class TestPurity:
    def test_an_analysis_comes_back_as_it_went_in(self, purity) -> None:
        wheat = register.require("wheat")
        analysis = an_analysis()
        result = analyse(analysis, wheat)

        purity.record("L-2024-0041", analysis, result, analysed_on=BOOKED)
        stored = purity.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert stored.analysis == analysis
        assert stored.analysed_on == BOOKED

    def test_the_percentages_are_kept_rather_than_worked_out_again(self, purity) -> None:
        wheat = register.require("wheat")
        result = analyse(an_analysis(), wheat)

        purity.record("L-2024-0041", an_analysis(), result, analysed_on=BOOKED)
        stored = purity.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert stored.pure_seed_percent == Decimal("98.4")
        assert stored.other_seed_percent == Decimal("0.8")
        assert stored.was_computed

    def test_an_analysis_that_was_never_worked_out_says_so(self, purity) -> None:
        purity.record("L-2024-0041", an_analysis(), None, analysed_on=BOOKED)
        stored = purity.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert not stored.was_computed
        assert stored.pure_seed_percent is None

    def test_the_weights_keep_the_precision_they_were_weighed_to(self, purity) -> None:
        purity.record("L-2024-0041", an_analysis(pure="118.20"), None, analysed_on=BOOKED)
        stored = purity.latest_for_lot("L-2024-0041")

        assert stored is not None
        assert str(stored.analysis.pure_seed_g) == "118.20"

    def test_a_second_analysis_does_not_replace_the_first(self, purity) -> None:
        purity.record("L-2024-0041", an_analysis(pure="118.2"), None, analysed_on=BOOKED)
        purity.record(
            "L-2024-0041", an_analysis(pure="118.6"), None, analysed_on=BOOKED, is_duplicate=True
        )

        both = purity.for_lot("L-2024-0041")

        assert len(both) == 2
        assert both[0].analysis.pure_seed_g == Decimal("118.2")
        assert both[1].is_duplicate

    def test_they_come_back_in_the_order_they_were_made(self, purity) -> None:
        for pure in ("118.0", "118.2", "118.4"):
            purity.record("L-2024-0041", an_analysis(pure=pure), None, analysed_on=BOOKED)

        weights = [stored.analysis.pure_seed_g for stored in purity.for_lot("L-2024-0041")]

        assert weights == [Decimal("118.0"), Decimal("118.2"), Decimal("118.4")]

    def test_a_lot_with_nothing_recorded_has_nothing(self, purity) -> None:
        assert purity.for_lot("L-2024-0041") == ()
        assert purity.latest_for_lot("L-2024-0041") is None

    def test_an_analysis_of_a_lot_that_does_not_exist_is_refused(self, purity) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            purity.record("L-2024-9999", an_analysis(), None, analysed_on=BOOKED)


class TestGermination:
    def test_a_test_comes_back_with_its_trays(self, germination) -> None:
        germination.record(a_test(96, 95, 97, 96))

        found = germination.for_lot("L-2024-0041")

        assert len(found) == 1
        assert len(found[0].replicates) == 4
        assert found[0].replicates[0].normal == 96

    def test_the_trays_keep_the_order_they_were_set_down_in(self, germination) -> None:
        germination.record(a_test(99, 95, 97, 93))

        found = germination.for_lot("L-2024-0041")[0]

        assert [tray.normal for tray in found.replicates] == [99, 95, 97, 93]

    def test_the_mean_survives_the_round_trip(self, germination) -> None:
        original = a_test(96, 95, 97, 96)

        germination.record(original)
        found = germination.for_lot("L-2024-0041")[0]

        assert found.mean_normal == original.mean_normal

    def test_a_retest_is_marked_as_one(self, germination) -> None:
        germination.record(a_test(96, 95, 97, 96))
        germination.record(a_test(94, 95, 94, 95, is_retest=True))

        found = germination.for_lot("L-2024-0041")

        assert not found[0].is_retest
        assert found[1].is_retest

    def test_the_dates_come_back_as_dates(self, germination) -> None:
        germination.record(a_test(96, 95, 97, 96))

        found = germination.for_lot("L-2024-0041")[0]

        assert found.set_down_on == date(2024, 9, 20)
        assert found.days_taken == 8

    def test_a_test_of_a_lot_that_does_not_exist_leaves_nothing_behind(
        self, germination, db
    ) -> None:
        orphan = GerminationTest(
            lot_reference="L-2024-9999",
            species_name="Triticum aestivum",
            replicates=(Replicate(96, 4, 0, 0, 0),) * 4,
            seeds_per_replicate=100,
            set_down_on=date(2024, 9, 20),
            final_count_on=date(2024, 9, 28),
            analyst="J. Whitfield",
        )

        with pytest.raises(sqlite3.IntegrityError):
            germination.record(orphan)

        # The trays must not survive a test that was rolled back.
        assert db.execute("select count(*) from germination_replicate").fetchone()[0] == 0

    def test_a_lot_with_no_tests_has_none(self, germination) -> None:
        assert germination.for_lot("L-2024-0041") == ()
