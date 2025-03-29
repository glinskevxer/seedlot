"""The printed form.

The widths matter here in a way they do not anywhere else in this project,
because the paper has boxes on it and the printer cannot see them. Several of
these tests are about a value that is too long for its box, which is the case
that would be found in production by a merchant ringing up to say their name is
cut in half on the certificate.
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
)
from arc.germination.model import Treatment
from arc.quantities import Percentage
from arc.reporting.certificate_form import WIDTH, render, render_many

STATION = {"station_name": "Ravenscar Seed Testing Station", "station_code": "GB-0214"}


def full_results(**overrides: object) -> Determinations:
    defaults: dict[str, object] = {
        "pure_seed": Percentage("98.4"),
        "other_seed": Percentage("0.8"),
        "inert_matter": Percentage("0.8"),
        "germination_percent": 96,
        "germination_tested_on": date(2024, 9, 28),
        "germination_treatment": Treatment.NONE,
    }
    defaults.update(overrides)
    return Determinations(**defaults)  # type: ignore[arg-type]


def a_certificate(
    *,
    results: Determinations | None = None,
    merchant: str = "Ravenscar Grain",
    kind: CertificateKind = CertificateKind.ORANGE_INTERNATIONAL,
    supersedes: CertificateNumber | None = None,
    withdrawn_on: date | None = None,
    serial: int = 187,
) -> Certificate:
    return Certificate(
        number=CertificateNumber("GB-0214", 2024, serial),
        kind=kind,
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        merchant=merchant,
        origin_country="GB",
        lot_weight_kg=Decimal("24000"),
        results=results if results is not None else full_results(),
        issued_on=date(2024, 10, 2),
        signed_by="A. Pearce",
        supersedes=supersedes,
        withdrawn_on=withdrawn_on,
    )


def printed(certificate: Certificate) -> str:
    return render(certificate, **STATION)


class TestTheShapeOfTheForm:
    def test_no_line_runs_past_the_perforation(self) -> None:
        for line in printed(a_certificate()).splitlines():
            assert len(line) <= WIDTH, line

    def test_the_station_is_at_the_top(self) -> None:
        lines = printed(a_certificate()).splitlines()

        assert "RAVENSCAR SEED TESTING STATION" in lines[0]
        assert "GB-0214" in lines[1]

    def test_the_kind_of_certificate_is_named(self) -> None:
        assert "ORANGE INTERNATIONAL SEED LOT" in printed(a_certificate())

    def test_it_ends_with_a_newline(self) -> None:
        assert printed(a_certificate()).endswith("\n")

    def test_the_labels_line_up(self) -> None:
        lines = printed(a_certificate()).splitlines()
        values = [line for line in lines if line.startswith("Lot ")]

        assert values[0].index("L-2024-0041") == 24


class TestWhatIsOnIt:
    def test_the_number_and_the_dates(self) -> None:
        form = printed(a_certificate())

        assert "GB-0214/2024/00187" in form
        assert "2024-10-02" in form

    def test_the_lot_and_who_it_belongs_to(self) -> None:
        form = printed(a_certificate())

        assert "L-2024-0041" in form
        assert "Ravenscar Grain" in form
        assert "24000 kg" in form

    def test_the_purity_figures(self) -> None:
        form = printed(a_certificate())

        assert "98.4 per cent by weight" in form
        assert "0.8 per cent by weight" in form

    def test_the_germination_with_its_date(self) -> None:
        form = printed(a_certificate())

        assert "96 percent normal seedlings" in form
        assert "2024-09-28" in form

    def test_a_treated_germination_says_so(self) -> None:
        results = full_results(germination_treatment=Treatment.KNO3)

        assert "after potassium nitrate" in printed(a_certificate(results=results))

    def test_a_replacement_names_what_it_supersedes(self) -> None:
        earlier = CertificateNumber("GB-0214", 2024, 186)

        assert "GB-0214/2024/00186" in printed(a_certificate(supersedes=earlier))

    def test_a_withdrawn_certificate_says_so_loudly(self) -> None:
        form = printed(a_certificate(withdrawn_on=date(2024, 11, 1)))

        assert "WITHDRAWN" in form


class TestWhatIsLeftOff:
    def test_a_determination_that_was_not_done_is_absent(self) -> None:
        form = printed(a_certificate())

        assert "Moisture" not in form
        assert "Thousand seed weight" not in form

    def test_one_that_was_done_is_there(self) -> None:
        results = full_results(moisture_percent=Decimal("14.0"))

        assert "14.0 per cent" in printed(a_certificate(results=results))

    def test_a_certificate_with_nothing_on_it_says_none(self) -> None:
        empty = Determinations()

        assert "none" in printed(a_certificate(results=empty))

    def test_a_search_prints_with_the_weight_it_went_through(self) -> None:
        report = OtherSeedReport(
            kind="complete",
            weight_examined_g=Decimal("1200.0"),
            counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),),
        )
        results = full_results(other_seed_report=report)

        assert "Avena fatua 4 in 1200.0 g" in printed(a_certificate(results=results))

    def test_a_targeted_search_lists_what_it_looked_for(self) -> None:
        report = OtherSeedReport(
            kind="limited",
            weight_examined_g=Decimal("1200.0"),
            sought=("Avena fatua", "Galium aparine"),
        )
        results = full_results(other_seed_report=report)

        assert "Avena fatua, Galium aparine" in printed(a_certificate(results=results))


class TestAValueTooLongForItsBox:
    def test_a_long_merchant_name_is_wrapped_not_cut(self) -> None:
        name = "Ravenscar Grain and Agricultural Merchants Cooperative Limited"

        form = printed(a_certificate(merchant=name))

        for word in name.split():
            assert word in form

    def test_and_the_wrapped_part_lines_up_under_the_first(self) -> None:
        name = "Ravenscar Grain and Agricultural Merchants Cooperative Limited"
        lines = printed(a_certificate(merchant=name)).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Merchant"))

        assert lines[start + 1].startswith(" " * 24)
        assert lines[start + 1][24] != " "

    def test_the_form_still_fits_the_paper(self) -> None:
        name = "Ravenscar Grain and Agricultural Merchants Cooperative Limited"

        for line in printed(a_certificate(merchant=name)).splitlines():
            assert len(line) <= WIDTH


class TestPrintingARun:
    def test_two_certificates_are_separated_by_a_form_feed(self) -> None:
        run = render_many((a_certificate(serial=187), a_certificate(serial=188)), **STATION)

        assert run.count("\f") == 1
        assert "GB-0214/2024/00187" in run
        assert "GB-0214/2024/00188" in run

    def test_one_certificate_has_no_form_feed(self) -> None:
        assert "\f" not in render_many((a_certificate(),), **STATION)

    def test_an_empty_run_prints_nothing(self) -> None:
        assert render_many((), **STATION) == ""
