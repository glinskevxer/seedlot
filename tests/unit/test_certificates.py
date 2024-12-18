"""The only thing that leaves the building."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
    check_certificate,
)
from arc.germination.model import Treatment
from arc.quantities import Percentage


def full_results(**overrides: object) -> Determinations:
    defaults: dict[str, object] = {
        "pure_seed": Percentage("98.4"),
        "other_seed": Percentage("0.8"),
        "inert_matter": Percentage("0.8"),
        "germination_percent": 96,
        "germination_tested_on": date(2024, 9, 28),
        "germination_treatment": Treatment.NONE,
        "moisture_percent": Decimal("14.0"),
        "thousand_seed_weight_g": Decimal("45.0"),
    }
    defaults.update(overrides)
    return Determinations(**defaults)  # type: ignore[arg-type]


def a_certificate(
    *,
    kind: CertificateKind = CertificateKind.ORANGE_INTERNATIONAL,
    results: Determinations | None = None,
    issued_on: date = date(2024, 10, 2),
    supersedes: CertificateNumber | None = None,
) -> Certificate:
    return Certificate(
        number=CertificateNumber("GB-0214", 2024, 187),
        kind=kind,
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        merchant="Ravenscar Grain",
        origin_country="GB",
        lot_weight_kg=Decimal("24000"),
        results=results if results is not None else full_results(),
        issued_on=issued_on,
        signed_by="A. Pearce",
        supersedes=supersedes,
    )


class TestTheNumber:
    def test_it_prints_the_way_the_sheet_is_headed(self) -> None:
        assert str(CertificateNumber("GB-0214", 2024, 187)) == "GB-0214/2024/00187"

    def test_it_parses_what_it_prints(self) -> None:
        assert CertificateNumber.parse("GB-0214/2024/00187") == CertificateNumber(
            "GB-0214", 2024, 187
        )

    def test_anything_else_is_refused(self) -> None:
        for bad in ("GB0214/2024/00187", "GB-0214/24/00187", "GB-0214/2024/187", ""):
            with pytest.raises(ValueError, match="not a certificate number"):
                CertificateNumber.parse(bad)

    def test_a_station_code_has_to_look_like_one(self) -> None:
        with pytest.raises(ValueError, match="not a station code"):
            CertificateNumber("GBR-021", 2024, 187)

    def test_numbers_sort_by_station_then_year_then_serial(self) -> None:
        assert sorted(
            [
                CertificateNumber("GB-0214", 2024, 900),
                CertificateNumber("GB-0214", 2023, 12),
                CertificateNumber("GB-0214", 2024, 7),
            ]
        ) == [
            CertificateNumber("GB-0214", 2023, 12),
            CertificateNumber("GB-0214", 2024, 7),
            CertificateNumber("GB-0214", 2024, 900),
        ]


class TestWhatWasDetermined:
    def test_a_full_set_lists_everything(self) -> None:
        assert full_results().determinations() == (
            "purity",
            "germination",
            "moisture",
            "thousand seed weight",
        )

    def test_a_determination_nobody_made_is_absent(self) -> None:
        results = Determinations(pure_seed=Percentage("99.0"))

        assert results.has_purity
        assert not results.has_germination
        assert results.germination_percent is None
        assert results.determinations() == ("purity",)

    def test_nothing_determined_at_all_lists_nothing(self) -> None:
        assert Determinations().determinations() == ()


class TestTheKinds:
    def test_only_the_orange_one_crosses_a_border(self) -> None:
        assert CertificateKind.ORANGE_INTERNATIONAL.crosses_borders
        assert not CertificateKind.BLUE_INTERNATIONAL.crosses_borders
        assert not CertificateKind.GREEN_ANALYSIS.crosses_borders

    def test_only_the_orange_one_needs_everything_on_it(self) -> None:
        assert CertificateKind.ORANGE_INTERNATIONAL.requires_full_analysis
        assert not CertificateKind.GREEN_ANALYSIS.requires_full_analysis


class TestWhenAGerminationStopsBeingQuotable:
    def test_it_runs_a_year_from_the_test_not_from_the_certificate(self) -> None:
        certificate = a_certificate()

        assert certificate.germination_valid_until() == date(2025, 9, 28)

    def test_it_is_current_up_to_and_including_the_last_day(self) -> None:
        certificate = a_certificate()

        assert certificate.germination_current_on(date(2025, 9, 28))
        assert not certificate.germination_current_on(date(2025, 9, 29))

    def test_a_certificate_with_no_germination_has_nothing_to_expire(self) -> None:
        certificate = a_certificate(results=Determinations(pure_seed=Percentage("99.0")))

        assert certificate.germination_valid_until() is None
        assert not certificate.germination_current_on(date(2024, 10, 2))


class TestWhatMayBeIssued:
    def test_a_complete_orange_certificate_raises_nothing(self) -> None:
        assert check_certificate(a_certificate()) == []

    def test_an_orange_one_without_a_purity_is_refused(self) -> None:
        broken = check_certificate(
            a_certificate(
                results=full_results(pure_seed=None, other_seed=None, inert_matter=None)
            )
        )

        assert "PURITY_MISSING" in [rule.code for rule in broken]

    def test_an_orange_one_without_a_germination_is_refused(self) -> None:
        broken = check_certificate(
            a_certificate(
                results=full_results(germination_percent=None, germination_tested_on=None)
            )
        )

        assert [rule.code for rule in broken] == ["GERMINATION_MISSING"]

    def test_a_green_one_may_carry_a_single_determination(self) -> None:
        certificate = a_certificate(
            kind=CertificateKind.GREEN_ANALYSIS,
            results=Determinations(moisture_percent=Decimal("14.0")),
        )

        assert check_certificate(certificate) == []

    def test_purity_components_that_do_not_sum_are_refused(self) -> None:
        broken = check_certificate(
            a_certificate(results=full_results(inert_matter=Percentage("0.9")))
        )

        assert [rule.code for rule in broken] == ["PURITY_DOES_NOT_SUM"]
        assert "100.1" in broken[0].detail

    def test_an_undated_germination_is_refused(self) -> None:
        broken = check_certificate(
            a_certificate(results=full_results(germination_tested_on=None))
        )

        assert [rule.code for rule in broken] == ["GERMINATION_UNDATED"]

    def test_a_germination_dated_after_the_certificate_is_refused(self) -> None:
        broken = check_certificate(
            a_certificate(
                results=full_results(germination_tested_on=date(2024, 10, 3)),
                issued_on=date(2024, 10, 2),
            )
        )

        assert [rule.code for rule in broken] == ["GERMINATION_AFTER_ISSUE"]

    def test_everything_wrong_comes_back_at_once(self) -> None:
        broken = check_certificate(
            a_certificate(
                results=Determinations(
                    pure_seed=Percentage("98.0"),
                    other_seed=Percentage("0.8"),
                    inert_matter=Percentage("0.8"),
                )
            )
        )

        assert [rule.code for rule in broken] == ["GERMINATION_MISSING", "PURITY_DOES_NOT_SUM"]


class TestReplacements:
    def test_an_ordinary_certificate_replaces_nothing(self) -> None:
        assert not a_certificate().is_replacement

    def test_a_replacement_names_what_it_supersedes(self) -> None:
        replaced = CertificateNumber("GB-0214", 2024, 187)
        replacement = a_certificate(supersedes=replaced)

        assert replacement.is_replacement
        assert replacement.supersedes == replaced

    def test_a_certificate_is_not_withdrawn_until_it_is(self) -> None:
        assert not a_certificate().is_withdrawn


class TestSayingWhatWasDoneToTheSample:
    def test_a_germination_with_no_treatment_stated_is_refused(self) -> None:
        # Not stated is not the same as nothing done. The first means the
        # record lost track of it.
        results = full_results(germination_treatment=None)

        broken = [rule.code for rule in check_certificate(a_certificate(results=results))]

        assert "GERMINATION_TREATMENT_NOT_STATED" in broken

    def test_a_germination_with_nothing_done_is_fine(self) -> None:
        results = full_results(germination_treatment=Treatment.NONE)

        assert check_certificate(a_certificate(results=results)) == []

    def test_a_treated_germination_is_fine_too(self) -> None:
        results = full_results(germination_treatment=Treatment.PRECHILL)

        assert check_certificate(a_certificate(results=results)) == []

    def test_no_germination_at_all_raises_nothing_about_treatments(self) -> None:
        results = full_results(
            germination_percent=None,
            germination_tested_on=None,
            germination_treatment=None,
        )

        broken = [rule.code for rule in check_certificate(a_certificate(results=results))]

        assert "GERMINATION_TREATMENT_NOT_STATED" not in broken


class TestHowTheGerminationIsPrinted:
    def test_an_untreated_germination_prints_plainly(self) -> None:
        results = full_results(germination_treatment=Treatment.NONE)

        assert results.germination_line == "96 percent normal seedlings"

    def test_a_treated_one_carries_the_treatment(self) -> None:
        results = full_results(germination_treatment=Treatment.KNO3)

        assert results.germination_line == (
            "96 percent normal seedlings after potassium nitrate"
        )

    def test_no_germination_prints_nothing_at_all(self) -> None:
        results = full_results(germination_percent=None)

        assert results.germination_line is None

    def test_a_treatment_that_was_never_stated_prints_the_bare_figure(self) -> None:
        # The certificate cannot be issued in this state anyway. Printing the
        # figure without inventing a treatment is the safe way to render it.
        results = full_results(germination_treatment=None)

        assert results.germination_line == "96 percent normal seedlings"
