"""What goes into the store when a certificate goes out."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.moisture.determination import Weighing, moisture_of
from arc.purity.analysis import PurityAnalysis, analyse
from arc.retention.model import Determination
from arc.retention.rules import check_repeat, needed_for
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.physical import MoistureRepository
from arc.storage.retention import RetentionRepository
from arc.workflow.issuing import issue
from arc.workflow.retaining import consumed_by

BOOKED = date(2024, 12, 2)
ISSUED = date(2024, 12, 18)
LOT = "L-2024-0041"


class Bench:
    def __init__(self, path) -> None:
        self.connection = open_test_database(path)
        self.lots = LotRepository(self.connection)
        self.purity = PurityRepository(self.connection)
        self.germination = GerminationRepository(self.connection)
        self.moisture = MoistureRepository(self.connection)
        self.certificates = CertificateRepository(self.connection)
        self.retention = RetentionRepository(self.connection)


@pytest.fixture
def bench(tmp_path):
    built = Bench(tmp_path / "arc.sqlite3")
    lot = make_lot()
    lot.move_to(LotStatus.SAMPLED)
    lot.move_to(LotStatus.IN_TEST)
    built.lots.save(lot, booked_in_on=BOOKED)
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
        analysed_on=date(2024, 12, 4),
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
            set_down_on=date(2024, 12, 5),
            final_count_on=date(2024, 12, 13),
            analyst="J. Whitfield",
        )
    )


def record_moisture(bench) -> None:
    weighing = Weighing(
        container_g=Decimal("12.000"),
        with_sample_g=Decimal("22.000"),
        after_drying_g=Decimal("20.600"),
    )
    bench.moisture.record(
        LOT,
        weighing,
        moisture_of(weighing),
        analyst="J. Whitfield",
        determined_on=date(2024, 12, 6),
    )


def issue_it(bench, kind=CertificateKind.ORANGE_INTERNATIONAL):
    return issue(
        LOT,
        kind,
        signed_by="A. Pearce",
        on=ISSUED,
        lots=bench.lots,
        purity=bench.purity,
        germination=bench.germination,
        certificates=bench.certificates,
        moisture=bench.moisture,
        retention=bench.retention,
    )


class TestWhatTheWorkTook:
    def test_a_purity_and_a_germination(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        certificate = issue_it(bench)

        assert consumed_by(certificate, register.require("wheat")) == Decimal("140.0")

    def test_adding_a_moisture_adds_its_sample(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        record_moisture(bench)
        certificate = issue_it(bench)

        assert consumed_by(certificate, register.require("wheat")) == Decimal("165.0")


class TestTheJarAfterwards:
    def test_a_sample_is_placed_when_the_certificate_is_issued(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        held = bench.retention.require(LOT)

        assert held.is_held is True
        assert held.held_from == ISSUED

    def test_what_is_left_is_the_kilogram_less_the_work(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        assert bench.retention.require(LOT).remaining_g == Decimal("860.0")

    def test_the_period_follows_the_certificate_that_was_issued(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        assert bench.retention.require(LOT).hold_until == date(2025, 12, 18)

    def test_nothing_is_placed_when_the_store_is_not_passed_in(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)

        issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
        )

        assert bench.retention.find(LOT) is None


class TestWhatTheJarCanStillDo:
    def test_it_can_cover_a_repeat_purity(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        held = bench.retention.require(LOT)

        assert (
            check_repeat(held, Determination.PURITY, register.require("wheat"), on=ISSUED) == []
        )

    def test_but_not_a_search(self, bench) -> None:
        # A search takes 1200 g and the jar is down to 860 g, which is the
        # whole reason the station is told what is left rather than assuming.
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        broken = check_repeat(
            bench.retention.require(LOT),
            Determination.OTHER_SEED,
            register.require("wheat"),
            on=ISSUED,
        )

        assert [rule.code for rule in broken] == ["SAMPLE_TOO_SMALL_TO_REPEAT"]

    def test_a_repeat_actually_drawn_comes_off_the_jar(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)

        bench.retention.draw(
            LOT,
            Determination.PURITY,
            needed_for(Determination.PURITY, register.require("wheat")),
            on=date(2025, 2, 3),
            analyst="R. Naylor",
        )

        assert bench.retention.require(LOT).remaining_g == Decimal("740.0")

    def test_a_second_certificate_resets_the_period(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        issue_it(bench)
        bench.lots.save(bench.lots.require(LOT), booked_in_on=BOOKED)
        issue_it(bench, CertificateKind.GREEN_ANALYSIS)

        assert bench.retention.require(LOT).certificate_kind is (CertificateKind.GREEN_ANALYSIS)
