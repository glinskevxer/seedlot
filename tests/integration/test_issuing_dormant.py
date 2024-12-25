"""A dormant lot, from the tray to the refusal.

The unit tests say the dormancy rules work. These say the rules are actually
consulted on the way to a certificate, which is a different claim: the rule
lived for one commit in a module nothing called, and a test at this level is
the only thing that would have noticed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.errors import RuleBroken
from arc.germination.model import GerminationTest, Replicate, Treatment
from arc.lots.model import LotStatus
from arc.purity.analysis import PurityAnalysis, analyse
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.workflow.issuing import gather, issue

BOOKED = date(2024, 11, 4)
ISSUED = date(2024, 11, 29)
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
        analysed_on=date(2024, 11, 6),
        is_duplicate=False,
    )


def record_germination(
    bench,
    *,
    normal: int = 96,
    fresh: int = 0,
    treatment: Treatment = Treatment.NONE,
    is_retest: bool = False,
    set_down: date = date(2024, 11, 5),
    counted: date = date(2024, 11, 13),
) -> None:
    bench.germination.record(
        GerminationTest(
            lot_reference=LOT,
            species_name="Triticum aestivum",
            replicates=tuple(
                Replicate(
                    normal=normal,
                    abnormal=100 - normal - fresh,
                    hard=0,
                    fresh=fresh,
                    dead=0,
                )
                for _ in range(4)
            ),
            seeds_per_replicate=100,
            set_down_on=set_down,
            final_count_on=counted,
            analyst="J. Whitfield",
            is_retest=is_retest,
            treatment=treatment,
        )
    )


def gathered(bench):
    return gather(
        LOT,
        "Triticum aestivum",
        purity=bench.purity,
        germination=bench.germination,
    )


def issue_it(bench):
    return issue(
        LOT,
        CertificateKind.ORANGE_INTERNATIONAL,
        signed_by="A. Pearce",
        on=ISSUED,
        lots=bench.lots,
        purity=bench.purity,
        germination=bench.germination,
        certificates=bench.certificates,
    )


class TestGatheringATreatedTest:
    def test_an_ordinary_test_reports_no_treatment(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)

        results = gathered(bench).results

        assert results.germination_percent == 96
        assert results.germination_treatment is Treatment.NONE

    def test_a_treated_retest_reports_the_treatment(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16, is_retest=True)
        record_germination(
            bench,
            normal=92,
            fresh=4,
            treatment=Treatment.PRECHILL,
            is_retest=True,
            set_down=date(2024, 11, 14),
            counted=date(2024, 11, 22),
        )

        results = gathered(bench).results

        assert results.germination_treatment is Treatment.PRECHILL

    def test_the_treatment_comes_off_the_test_that_is_being_reported(self, bench) -> None:
        # Two tests, and it is the later one whose figure goes on the sheet, so
        # it has to be the later one whose treatment does too.
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16, treatment=Treatment.KNO3, is_retest=True)
        record_germination(
            bench,
            normal=92,
            fresh=4,
            treatment=Treatment.PRECHILL,
            is_retest=True,
            set_down=date(2024, 11, 14),
            counted=date(2024, 11, 22),
        )

        assert gathered(bench).results.germination_treatment is Treatment.PRECHILL


class TestADormantLotCannotBeCertified:
    def test_gathering_a_dormant_untreated_test_raises_the_problem(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16)

        result = gathered(bench)

        assert result.is_ready is False
        assert "DORMANCY_NOT_BROKEN" in [rule.code for rule in result.problems]

    def test_and_issuing_is_refused(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16)

        with pytest.raises(RuleBroken) as refused:
            issue_it(bench)

        assert "DORMANCY_NOT_BROKEN" in refused.value.codes

    def test_the_lot_stays_in_test_after_the_refusal(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16)

        with pytest.raises(RuleBroken):
            issue_it(bench)

        assert bench.lots.require(LOT).status is LotStatus.IN_TEST

    def test_treating_the_sample_and_repeating_clears_it(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16, is_retest=True)
        record_germination(
            bench,
            normal=92,
            fresh=4,
            treatment=Treatment.PRECHILL,
            is_retest=True,
            set_down=date(2024, 11, 14),
            counted=date(2024, 11, 22),
        )

        certificate = issue_it(bench)

        assert certificate.results.germination_treatment is Treatment.PRECHILL
        assert bench.lots.require(LOT).status is LotStatus.REPORTED

    def test_the_treatment_survives_being_read_back(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, normal=80, fresh=16, is_retest=True)
        record_germination(
            bench,
            normal=92,
            fresh=4,
            treatment=Treatment.PRECHILL,
            is_retest=True,
            set_down=date(2024, 11, 14),
            counted=date(2024, 11, 22),
        )
        issued = issue_it(bench)

        recovered = bench.certificates.require(str(issued.number))

        assert recovered.results.germination_treatment is Treatment.PRECHILL
        assert recovered.results.germination_line.endswith("after prechill")

    def test_a_treatment_off_the_handbook_stops_the_certificate(self, bench) -> None:
        record_purity(bench)
        record_germination(bench, treatment=Treatment.SCARIFY, is_retest=True)

        with pytest.raises(RuleBroken) as refused:
            issue_it(bench)

        assert "TREATMENT_NOT_ALLOWED" in refused.value.codes
