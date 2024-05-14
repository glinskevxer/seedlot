"""Issuing a certificate from what the station recorded."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from arc.certificates.model import CertificateKind
from arc.errors import RuleBroken
from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.purity.analysis import PurityAnalysis, analyse
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.schema import connect, migrate
from tests.support import open_test_database
from arc.workflow.issuing import gather, issue
from tests.conftest import make_lot

BOOKED = date(2024, 9, 18)
ISSUED = date(2024, 10, 2)


class Station:
    """The four repositories a job touches, opened on one connection."""

    def __init__(self, path) -> None:
        self.connection = open_test_database(path)
        self.lots = LotRepository(self.connection)
        self.purity = PurityRepository(self.connection)
        self.germination = GerminationRepository(self.connection)
        self.certificates = CertificateRepository(self.connection)


@pytest.fixture
def station(tmp_path):
    built = Station(tmp_path / "arc.sqlite3")
    lot = make_lot()
    lot.move_to(LotStatus.SAMPLED)
    lot.move_to(LotStatus.IN_TEST)
    built.lots.save(lot, booked_in_on=BOOKED)
    yield built
    built.connection.close()


def record_purity(
    station,
    pure: str = "118.2",
    other: str = "0.9",
    inert: str = "0.9",
    *,
    duplicate: bool = False,
) -> None:
    analysis = PurityAnalysis(
        working_sample_g=Decimal("120.0"),
        pure_seed_g=Decimal(pure),
        other_seed_g=Decimal(other),
        inert_matter_g=Decimal(inert),
        analyst="J. Whitfield",
    )
    station.purity.record(
        "L-2024-0041",
        analysis,
        analyse(analysis, register.require("wheat")),
        analysed_on=date(2024, 9, 24),
        is_duplicate=duplicate,
    )


def record_germination(station, *normals: int, is_retest: bool = False) -> None:
    station.germination.record(
        GerminationTest(
            lot_reference="L-2024-0041",
            species_name="Triticum aestivum",
            replicates=tuple(
                Replicate(normal=n, abnormal=100 - n, hard=0, fresh=0, dead=0)
                for n in normals
            ),
            seeds_per_replicate=100,
            set_down_on=date(2024, 9, 20),
            final_count_on=date(2024, 9, 28),
            analyst="J. Whitfield",
            is_retest=is_retest,
        )
    )


class TestGathering:
    def test_a_lot_with_nothing_done_to_it_gathers_nothing(self, station) -> None:
        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert gathered.is_ready
        assert gathered.results.determinations() == ()

    def test_a_recorded_purity_comes_through(self, station) -> None:
        record_purity(station)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert gathered.results.has_purity
        assert str(gathered.results.pure_seed) == "98.4"

    def test_a_settled_germination_comes_through_with_its_date(self, station) -> None:
        record_germination(station, 96, 95, 97, 96)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert gathered.results.germination_percent == 96
        assert gathered.results.germination_tested_on == date(2024, 9, 28)

    def test_an_unsettled_germination_is_a_problem_rather_than_a_figure(
        self, station
    ) -> None:
        record_germination(station, 99, 96, 92, 87)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert not gathered.is_ready
        assert [rule.code for rule in gathered.problems] == ["GERMINATION_NOT_SETTLED"]
        assert gathered.results.germination_percent is None

    def test_a_repeat_that_settles_it_is_used(self, station) -> None:
        record_germination(station, 99, 96, 92, 87)
        record_germination(station, 94, 95, 94, 95, is_retest=True)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert gathered.is_ready
        assert gathered.results.germination_percent == 95

    def test_duplicate_purity_analyses_that_agree_are_accepted(self, station) -> None:
        record_purity(station, "118.2")
        record_purity(station, "118.4", duplicate=True)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert gathered.is_ready

    def test_duplicates_that_disagree_stop_the_certificate(self, station) -> None:
        # 98.4 against 97.5, which is 0.9 apart where wheat is allowed 0.81.
        record_purity(station, "118.2")
        record_purity(station, "117.1", "1.5", "1.4", duplicate=True)

        gathered = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )

        assert not gathered.is_ready
        assert [rule.code for rule in gathered.problems] == ["PURITY_DUPLICATES_DISAGREE"]

    def test_the_allowance_used_is_the_one_for_that_species(self, station) -> None:
        # The same two analyses are compared against a wider allowance when the
        # seed is chaffy. Passing the species in is what makes that possible.
        record_purity(station, "118.2")
        record_purity(station, "117.1", "1.5", "1.4", duplicate=True)

        as_wheat = gather(
            "L-2024-0041",
            "Triticum aestivum",
            purity=station.purity,
            germination=station.germination,
        )
        as_grass = gather(
            "L-2024-0041",
            "Lolium perenne",
            purity=station.purity,
            germination=station.germination,
        )

        assert not as_wheat.is_ready
        assert as_grass.is_ready


class TestIssuing:
    def test_a_complete_lot_gets_a_certificate(self, station) -> None:
        record_purity(station)
        record_germination(station, 96, 95, 97, 96)

        certificate = issue(
            "L-2024-0041",
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
        )

        assert str(certificate.number) == "GB-0214/2024/00001"
        assert certificate.results.germination_percent == 96

    def test_the_lot_moves_to_reported(self, station) -> None:
        record_purity(station)
        record_germination(station, 96, 95, 97, 96)

        issue(
            "L-2024-0041",
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
        )

        assert station.lots.require("L-2024-0041").status is LotStatus.REPORTED

    def test_an_orange_certificate_without_a_germination_is_refused(self, station) -> None:
        record_purity(station)

        with pytest.raises(RuleBroken) as caught:
            issue(
                "L-2024-0041",
                CertificateKind.ORANGE_INTERNATIONAL,
                signed_by="A. Pearce",
                on=ISSUED,
                lots=station.lots,
                purity=station.purity,
                germination=station.germination,
                certificates=station.certificates,
            )

        assert "GERMINATION_MISSING" in caught.value.codes

    def test_a_green_one_may_carry_the_purity_alone(self, station) -> None:
        record_purity(station)

        certificate = issue(
            "L-2024-0041",
            CertificateKind.GREEN_ANALYSIS,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
        )

        assert certificate.results.determinations() == ("purity",)

    def test_nothing_is_issued_when_the_germination_is_unsettled(self, station) -> None:
        record_purity(station)
        record_germination(station, 99, 96, 92, 87)

        with pytest.raises(RuleBroken):
            issue(
                "L-2024-0041",
                CertificateKind.ORANGE_INTERNATIONAL,
                signed_by="A. Pearce",
                on=ISSUED,
                lots=station.lots,
                purity=station.purity,
                germination=station.germination,
                certificates=station.certificates,
            )

        assert station.certificates.for_lot("L-2024-0041") == ()
        assert station.lots.require("L-2024-0041").status is LotStatus.IN_TEST

    def test_the_second_certificate_of_the_year_takes_the_next_number(
        self, station
    ) -> None:
        record_purity(station)

        first = issue(
            "L-2024-0041",
            CertificateKind.GREEN_ANALYSIS,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
        )
        second = issue(
            "L-2024-0041",
            CertificateKind.GREEN_ANALYSIS,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
        )

        assert first.number.serial == 1
        assert second.number.serial == 2
