"""A lot walking through its statuses as the work happens.

The status machine will not let a lot skip a step, and nothing was walking it,
so every lot booked in from the console stayed booked in for ever. These are
the tests that would have caught that: they follow one lot from the bag to the
certificate and check the Monday morning list gets shorter.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.purity.analysis import PurityAnalysis, analyse
from arc.reporting.registers import work_in_progress
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.workflow.issuing import issue
from arc.workflow.progress import begin_testing, mark_reported

BOOKED = date(2025, 3, 3)
TODAY = date(2025, 3, 26)
LOT = "L-2024-0041"


class Bench:
    def __init__(self, path) -> None:
        self.connection = open_test_database(path)
        self.lots = LotRepository(self.connection)
        self.purity = PurityRepository(self.connection)
        self.germination = GerminationRepository(self.connection)
        self.certificates = CertificateRepository(self.connection)


@pytest.fixture
def bench(tmp_path):
    built = Bench(tmp_path / "arc.sqlite3")
    built.lots.save(make_lot(), booked_in_on=BOOKED)
    yield built
    built.connection.close()


def record_purity(bench) -> None:
    analysis = PurityAnalysis(
        working_sample_g=Decimal("120.0"),
        pure_seed_g=Decimal("118.2"),
        other_seed_g=Decimal("0.9"),
        inert_matter_g=Decimal("0.9"),
        analyst="J. Whitfield",
    )
    bench.purity.record(
        LOT,
        analysis,
        analyse(analysis, register.require("wheat")),
        analysed_on=date(2025, 3, 5),
        is_duplicate=False,
    )


def record_germination(bench) -> None:
    bench.germination.record(
        GerminationTest(
            lot_reference=LOT,
            species_name="Triticum aestivum",
            replicates=tuple(
                Replicate(normal=n, abnormal=100 - n, hard=0, fresh=0, dead=0)
                for n in (96, 95, 97, 96)
            ),
            seeds_per_replicate=100,
            set_down_on=date(2025, 3, 6),
            final_count_on=date(2025, 3, 14),
            analyst="J. Whitfield",
        )
    )


class TestPuttingALotOnTheBench:
    def test_a_freshly_booked_lot_is_only_booked_in(self, bench) -> None:
        assert bench.lots.require(LOT).status is LotStatus.BOOKED_IN

    def test_beginning_the_testing_walks_it_two_steps(self, bench) -> None:
        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.IN_TEST

    def test_and_the_move_is_saved(self, bench) -> None:
        lot = bench.lots.require(LOT)
        begin_testing(lot, bench.lots, on=TODAY)

        reopened = bench.lots.require(LOT)

        assert reopened.status is LotStatus.IN_TEST

    def test_doing_it_twice_changes_nothing(self, bench) -> None:
        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)
        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.IN_TEST

    def test_a_lot_already_sampled_only_needs_one_step(self, bench) -> None:
        lot = bench.lots.require(LOT)
        lot.move_to(LotStatus.SAMPLED)
        bench.lots.save(lot, booked_in_on=BOOKED)

        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.IN_TEST

    def test_a_reported_lot_is_left_alone(self, bench) -> None:
        # A repeat test on a certified lot happens, and it does not put the
        # lot back in the queue.
        mark_reported(bench.lots.require(LOT), bench.lots, on=TODAY)

        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.REPORTED


class TestReporting:
    def test_it_walks_the_whole_way_from_booked_in(self, bench) -> None:
        mark_reported(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.REPORTED

    def test_from_in_test_as_well(self, bench) -> None:
        begin_testing(bench.lots.require(LOT), bench.lots, on=TODAY)

        mark_reported(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.REPORTED

    def test_a_closed_lot_is_left_alone(self, bench) -> None:
        lot = bench.lots.require(LOT)
        lot.move_to(LotStatus.CLOSED)
        bench.lots.save(lot, booked_in_on=BOOKED)

        mark_reported(bench.lots.require(LOT), bench.lots, on=TODAY)

        assert bench.lots.require(LOT).status is LotStatus.CLOSED


class TestIssuingWalksIt:
    def test_a_lot_never_marked_as_on_the_bench_still_gets_reported(self, bench) -> None:
        # This is the bug. Issuing only moved a lot that was already in test,
        # and nothing put it there, so a certified lot stayed booked in.
        record_purity(bench)
        record_germination(bench)

        issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=TODAY,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
        )

        assert bench.lots.require(LOT).status is LotStatus.REPORTED

    def test_and_it_comes_off_the_monday_morning_list(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)

        assert len(work_in_progress(bench.lots, bench.certificates)) == 1

        issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=TODAY,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
        )

        assert work_in_progress(bench.lots, bench.certificates) == ()

    def test_a_refused_certificate_leaves_the_lot_where_it_was(self, bench) -> None:
        record_purity(bench)

        from arc.errors import RuleBroken

        with pytest.raises(RuleBroken):
            issue(
                LOT,
                CertificateKind.ORANGE_INTERNATIONAL,
                signed_by="A. Pearce",
                on=TODAY,
                lots=bench.lots,
                purity=bench.purity,
                germination=bench.germination,
                certificates=bench.certificates,
            )

        assert bench.lots.require(LOT).status is LotStatus.BOOKED_IN
