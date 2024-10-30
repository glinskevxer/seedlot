"""A search for other species, from the bench through to the certificate.

Everything here goes through the real repositories. The point is not that the
rules work, which the unit tests already say, but that the search recorded at
the bench is the one that reaches the certificate, with the weight it went
through and a rate worked out from that weight rather than assumed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.errors import RuleBroken
from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.purity.analysis import PurityAnalysis, analyse
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository
from arc.workflow.issuing import gather, issue

BOOKED = date(2024, 9, 18)
SEARCHED = date(2024, 9, 26)
ISSUED = date(2024, 10, 2)
LOT = "L-2024-0041"


class Bench:
    """Every repository a job touches, opened on one connection."""

    def __init__(self, path) -> None:
        self.connection = open_test_database(path)
        self.lots = LotRepository(self.connection)
        self.purity = PurityRepository(self.connection)
        self.germination = GerminationRepository(self.connection)
        self.other_seed = OtherSeedRepository(self.connection)
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


def record_purity(bench, other: str = "0.9") -> None:
    pure = Decimal("120.0") - Decimal(other) - Decimal("0.9")
    analysis = PurityAnalysis(
        working_sample_g=Decimal("120.0"),
        pure_seed_g=pure,
        other_seed_g=Decimal(other),
        inert_matter_g=Decimal("0.9"),
        analyst="J. Whitfield",
    )
    bench.purity.record(
        LOT,
        analysis,
        analyse(analysis, register.require("wheat")),
        analysed_on=date(2024, 9, 24),
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
            set_down_on=date(2024, 9, 20),
            final_count_on=date(2024, 9, 28),
            analyst="J. Whitfield",
        )
    )


def record_search(
    bench,
    *,
    kind: SearchKind = SearchKind.COMPLETE,
    weight: str = "1200.0",
    findings: tuple[Finding, ...] = (),
    sought: tuple[str, ...] = (),
) -> None:
    bench.other_seed.record(
        LOT,
        OtherSeedSearch(
            species_name="Triticum aestivum",
            kind=kind,
            weight_examined_g=Decimal(weight),
            findings=findings,
            sought=sought,
            analyst="J. Whitfield",
        ),
        searched_on=SEARCHED,
    )


def gathered_for(bench):
    return gather(
        LOT,
        "Triticum aestivum",
        purity=bench.purity,
        germination=bench.germination,
        other_seed=bench.other_seed,
    )


class TestGatheringTheSearch:
    def test_no_search_leaves_the_field_absent(self, bench) -> None:
        record_purity(bench)

        assert gathered_for(bench).results.other_seed_report is None

    def test_a_search_comes_through_with_its_weight(self, bench) -> None:
        record_purity(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))

        report = gathered_for(bench).results.other_seed_report

        assert report is not None
        assert report.kind == "complete"
        assert report.weight_examined_g == Decimal("1200.0")

    def test_the_rate_is_worked_out_from_the_weight_that_was_searched(self, bench) -> None:
        record_purity(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))

        report = gathered_for(bench).results.other_seed_report

        assert report is not None
        assert report.counts[0].count == 4
        assert report.counts[0].per_kg == Decimal("3.3")

    def test_the_same_count_off_a_reduced_search_reads_five_times_higher(self, bench) -> None:
        record_purity(bench)
        record_search(
            bench,
            kind=SearchKind.REDUCED,
            weight="240.0",
            findings=(Finding("Avena fatua", 4),),
            sought=("Avena fatua",),
        )

        report = gathered_for(bench).results.other_seed_report

        assert report is not None
        assert report.counts[0].per_kg == Decimal("16.7")

    def test_the_latest_search_is_the_one_that_counts(self, bench) -> None:
        record_purity(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))
        record_search(bench, findings=(Finding("Avena fatua", 7),))

        report = gathered_for(bench).results.other_seed_report

        assert report is not None
        assert report.counts[0].count == 7

    def test_a_nil_return_is_gathered_as_a_result_not_as_nothing(self, bench) -> None:
        record_purity(bench, other="0.0")
        record_search(bench)

        report = gathered_for(bench).results.other_seed_report

        assert report is not None
        assert report.is_nil is True
        assert report.line() == "none found in 1200.0 g, complete search"


class TestIssuingWithASearch:
    def issue_it(self, bench, kind=CertificateKind.ORANGE_INTERNATIONAL):
        return issue(
            LOT,
            kind,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
            other_seed=bench.other_seed,
        )

    def test_the_search_reaches_the_certificate(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))

        certificate = self.issue_it(bench)

        report = certificate.results.other_seed_report
        assert report is not None
        assert report.counts[0].species_name == "Avena fatua"

    def test_and_survives_being_read_back_out_of_the_database(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))
        issued = self.issue_it(bench)

        recovered = bench.certificates.require(str(issued.number))

        report = recovered.results.other_seed_report
        assert report is not None
        assert report.counts[0].per_kg == Decimal("3.3")
        assert report.weight_examined_g == Decimal("1200.0")

    def test_a_reduced_search_stops_an_orange_certificate(self, bench) -> None:
        record_purity(bench)
        record_germination(bench)
        record_search(
            bench,
            kind=SearchKind.REDUCED,
            weight="240.0",
            findings=(Finding("Avena fatua", 4),),
            sought=("Avena fatua",),
        )

        with pytest.raises(RuleBroken) as refused:
            self.issue_it(bench)

        assert "OTHER_SEED_SEARCH_TOO_NARROW" in refused.value.codes

    def test_a_complete_search_finding_none_of_what_purity_weighed_stops_it(
        self, bench
    ) -> None:
        record_purity(bench, other="0.9")
        record_germination(bench)
        record_search(bench)

        with pytest.raises(RuleBroken) as refused:
            self.issue_it(bench)

        assert "OTHER_SEED_CONTRADICTS_PURITY" in refused.value.codes

    def test_and_the_lot_is_left_in_test_when_the_certificate_is_refused(self, bench) -> None:
        record_purity(bench, other="0.9")
        record_germination(bench)
        record_search(bench)

        with pytest.raises(RuleBroken):
            self.issue_it(bench)

        assert bench.lots.require(LOT).status is LotStatus.IN_TEST

    def test_a_certificate_issued_without_the_repository_carries_no_search(self, bench) -> None:
        # The argument is optional so that the older commands keep working,
        # and leaving it out has to mean no search rather than an empty one.
        record_purity(bench)
        record_germination(bench)
        record_search(bench, findings=(Finding("Avena fatua", 4),))

        certificate = issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
        )

        assert certificate.results.other_seed_report is None
