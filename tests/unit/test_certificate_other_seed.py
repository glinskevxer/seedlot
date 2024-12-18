"""The rules the search has to pass before it can go on a certificate.

These are the ones where two determinations judge each other rather than each
being judged on its own. A search is fine, a purity analysis is fine, and the
pair of them together can still be a certificate that must not be issued.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
    OtherSeedCount,
    OtherSeedReport,
    check_certificate,
)
from arc.germination.model import Treatment
from arc.quantities import Percentage


def a_report(
    *,
    kind: str = "complete",
    weight: str = "1200.0",
    counts: tuple[OtherSeedCount, ...] = (),
    sought: tuple[str, ...] = (),
) -> OtherSeedReport:
    return OtherSeedReport(
        kind=kind,
        weight_examined_g=Decimal(weight),
        counts=counts,
        sought=sought,
    )


def results_with(report: OtherSeedReport | None, **overrides: object) -> Determinations:
    defaults: dict[str, object] = {
        "pure_seed": Percentage("98.4"),
        "other_seed": Percentage("0.8"),
        "inert_matter": Percentage("0.8"),
        "germination_percent": 96,
        "germination_tested_on": date(2024, 9, 28),
        "germination_treatment": Treatment.NONE,
        "other_seed_report": report,
    }
    defaults.update(overrides)
    return Determinations(**defaults)  # type: ignore[arg-type]


def a_certificate(
    results: Determinations,
    kind: CertificateKind = CertificateKind.ORANGE_INTERNATIONAL,
) -> Certificate:
    return Certificate(
        number=CertificateNumber("GB-0214", 2024, 187),
        kind=kind,
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        merchant="Ravenscar Grain",
        origin_country="GB",
        lot_weight_kg=Decimal("24000"),
        results=results,
        issued_on=date(2024, 10, 2),
        signed_by="A. Pearce",
    )


def codes(certificate: Certificate) -> list[str]:
    return [rule.code for rule in check_certificate(certificate)]


class TestWhatTheReportSaysAboutItself:
    def test_no_counts_at_all_is_a_nil_return(self) -> None:
        assert a_report().is_nil is True

    def test_a_count_of_zero_is_also_a_nil_return(self) -> None:
        report = a_report(counts=(OtherSeedCount("Avena fatua", 0, Decimal("0.0")),))

        assert report.is_nil is True

    def test_one_seed_is_not(self) -> None:
        report = a_report(counts=(OtherSeedCount("Avena fatua", 1, Decimal("0.8")),))

        assert report.is_nil is False

    def test_the_printed_line_carries_the_weight_and_the_kind(self) -> None:
        assert a_report().line() == "none found in 1200.0 g, complete search"

    def test_and_the_species_when_there_are_some(self) -> None:
        report = a_report(
            counts=(
                OtherSeedCount("Avena fatua", 4, Decimal("3.3")),
                OtherSeedCount("Galium aparine", 1, Decimal("0.8")),
            )
        )

        assert report.line() == ("Avena fatua 4, Galium aparine 1 in 1200.0 g, complete search")

    def test_a_search_counts_as_a_determination_that_was_done(self) -> None:
        results = results_with(a_report())

        assert "other seed by number" in results.determinations()

    def test_and_no_search_does_not(self) -> None:
        assert "other seed by number" not in results_with(None).determinations()


class TestASearchNeedsAPurityAnalysisBesideIt:
    def test_a_search_with_no_purity_is_refused(self) -> None:
        results = results_with(a_report(), pure_seed=None, other_seed=None, inert_matter=None)

        assert "OTHER_SEED_WITHOUT_PURITY" in codes(a_certificate(results))

    def test_a_search_with_a_purity_analysis_is_fine(self) -> None:
        # The search has to have found the seeds the purity analysis weighed,
        # or the pair of them trips the contradiction rule further down.
        found = a_report(counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),))

        assert codes(a_certificate(results_with(found))) == []

    def test_no_search_and_no_purity_does_not_raise_this_one(self) -> None:
        results = results_with(None, pure_seed=None, other_seed=None, inert_matter=None)

        assert "OTHER_SEED_WITHOUT_PURITY" not in codes(a_certificate(results))


class TestWhichSearchesCrossABorder:
    def test_a_complete_search_can_go_on_an_orange_certificate(self) -> None:
        found = a_report(counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),))

        assert codes(a_certificate(results_with(found))) == []

    def test_a_limited_one_cannot(self) -> None:
        # The orange certificate is the one a customs officer in another
        # country reads. A figure that only covers three species it was asked
        # about is not the other seed content of the lot.
        results = results_with(a_report(kind="limited", sought=("Avena fatua",)))

        assert "OTHER_SEED_SEARCH_TOO_NARROW" in codes(a_certificate(results))

    def test_nor_can_a_reduced_one(self) -> None:
        results = results_with(
            a_report(kind="reduced", weight="240.0", sought=("Avena fatua",))
        )

        assert "OTHER_SEED_SEARCH_TOO_NARROW" in codes(a_certificate(results))

    def test_a_green_report_can_carry_a_limited_search(self) -> None:
        # A green report answers the question the customer asked and does not
        # pretend to be a full analysis, so a targeted search is the right
        # thing on it.
        results = results_with(
            a_report(
                kind="limited",
                sought=("Avena fatua",),
                counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),),
            )
        )

        assert codes(a_certificate(results, CertificateKind.GREEN_ANALYSIS)) == []

    def test_a_targeted_search_still_has_to_say_what_it_looked_for(self) -> None:
        results = results_with(a_report(kind="limited", sought=()))
        certificate = a_certificate(results, CertificateKind.GREEN_ANALYSIS)

        assert "OTHER_SEED_SEARCH_UNSTATED" in codes(certificate)

    def test_a_complete_search_does_not_need_a_list(self) -> None:
        certificate = a_certificate(results_with(a_report()))

        assert "OTHER_SEED_SEARCH_UNSTATED" not in codes(certificate)


class TestWhenTheTwoDeterminationsDisagree:
    def test_weighed_other_seed_and_a_complete_search_that_found_none(self) -> None:
        # 0.8 percent of a 120 g working sample is nearly a gram of seed that
        # is not wheat. Searching ten times that much and finding nothing is
        # not a clean lot, it is two results that cannot both be right.
        results = results_with(a_report(), other_seed=Percentage("0.8"))

        assert "OTHER_SEED_CONTRADICTS_PURITY" in codes(a_certificate(results))

    def test_unless_the_search_found_something_too(self) -> None:
        report = a_report(counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),))
        results = results_with(report, other_seed=Percentage("0.8"))

        assert codes(a_certificate(results)) == []

    def test_and_a_purity_analysis_that_found_none_agrees_with_a_nil_return(
        self,
    ) -> None:
        results = results_with(
            a_report(),
            pure_seed=Percentage("99.2"),
            other_seed=Percentage("0.0"),
            inert_matter=Percentage("0.8"),
        )

        assert codes(a_certificate(results)) == []

    def test_a_limited_search_finding_nothing_is_not_a_contradiction(self) -> None:
        # It was only ever looking for one species. Its nil return says
        # nothing about whatever the purity analysis weighed out.
        report = a_report(kind="limited", sought=("Avena fatua",))
        results = results_with(report, other_seed=Percentage("0.8"))
        certificate = a_certificate(results, CertificateKind.GREEN_ANALYSIS)

        assert "OTHER_SEED_CONTRADICTS_PURITY" not in codes(certificate)

    def test_a_search_recorded_with_a_zero_count_still_contradicts(self) -> None:
        report = a_report(counts=(OtherSeedCount("Avena fatua", 0, Decimal("0.0")),))
        results = results_with(report, other_seed=Percentage("0.8"))

        assert "OTHER_SEED_CONTRADICTS_PURITY" in codes(a_certificate(results))

    def test_no_search_means_nothing_to_contradict(self) -> None:
        assert codes(a_certificate(results_with(None))) == []
