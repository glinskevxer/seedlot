"""The register of searches, and the search columns on the certificate one.

The distinction being tested throughout is between an empty cell and a cell
that says none. One means nobody looked. The other means somebody looked
through a named weight of seed and found nothing, and a merchant pays for the
second and not for the first.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
    OtherSeedCount,
    OtherSeedReport,
)
from arc.lots.model import LotStatus
from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.quantities import Percentage
from arc.reporting.registers import certificate_register, other_seed_register
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository

BOOKED = date(2024, 9, 18)
SEARCHED = date(2024, 9, 26)
LOT = "L-2024-0041"


@pytest.fixture
def station(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    lots = LotRepository(connection)
    lot = make_lot()
    lot.move_to(LotStatus.SAMPLED)
    lots.save(lot, booked_in_on=BOOKED)
    yield lots, OtherSeedRepository(connection), CertificateRepository(connection)
    connection.close()


def record(
    searches,
    *,
    kind: SearchKind = SearchKind.COMPLETE,
    weight: str = "1200.0",
    findings: tuple[Finding, ...] = (),
    sought: tuple[str, ...] = (),
    reference: str = LOT,
) -> None:
    searches.record(
        reference,
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


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


class TestTheSearchRegister:
    def test_a_station_that_has_searched_nothing_still_has_a_header(self, station) -> None:
        lots, searches, _ = station

        sheet = rows(other_seed_register(lots, searches))

        assert sheet == []

    def test_a_nil_return_reads_as_none_rather_than_as_blank(self, station) -> None:
        lots, searches, _ = station
        record(searches)

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["found"] == "none"

    def test_a_finding_is_named_with_its_count(self, station) -> None:
        lots, searches, _ = station
        record(searches, findings=(Finding("Avena fatua", 4),))

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["found"] == "Avena fatua 4"

    def test_two_findings_are_both_listed(self, station) -> None:
        lots, searches, _ = station
        record(
            searches,
            findings=(Finding("Avena fatua", 4), Finding("Galium aparine", 2)),
        )

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["found"] == "Avena fatua 4, Galium aparine 2"

    def test_the_weight_and_the_kind_are_both_columns(self, station) -> None:
        lots, searches, _ = station
        record(searches, kind=SearchKind.REDUCED, weight="240.0", sought=("Avena fatua",))

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["weight examined g"] == "240.0"
        assert sheet[0]["kind"] == "reduced"

    def test_the_sought_species_are_separated_so_the_cell_can_be_read(self, station) -> None:
        lots, searches, _ = station
        record(
            searches,
            kind=SearchKind.LIMITED,
            sought=("Avena fatua", "Galium aparine"),
        )

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["sought"] == "Avena fatua; Galium aparine"

    def test_a_complete_search_leaves_the_sought_cell_empty(self, station) -> None:
        lots, searches, _ = station
        record(searches)

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["sought"] == ""

    def test_every_search_on_a_lot_gets_a_row(self, station) -> None:
        lots, searches, _ = station
        record(searches, findings=(Finding("Avena fatua", 4),))
        record(searches, findings=(Finding("Avena fatua", 7),))

        sheet = rows(other_seed_register(lots, searches))

        assert [row["found"] for row in sheet] == ["Avena fatua 4", "Avena fatua 7"]

    def test_the_lot_and_the_merchant_come_off_the_lot(self, station) -> None:
        lots, searches, _ = station
        record(searches)

        sheet = rows(other_seed_register(lots, searches))

        assert sheet[0]["lot"] == LOT
        assert sheet[0]["merchant"] == "Ravenscar Grain"
        assert sheet[0]["analyst"] == "J. Whitfield"


class TestTheSearchColumnsOnTheCertificateRegister:
    def issue(self, certificates, report: OtherSeedReport | None) -> None:
        certificates.issue(
            Certificate(
                number=CertificateNumber("GB-0214", 2024, 187),
                kind=CertificateKind.ORANGE_INTERNATIONAL,
                lot_reference=LOT,
                species_name="Triticum aestivum",
                merchant="Ravenscar Grain",
                origin_country="GB",
                lot_weight_kg=Decimal("24000"),
                results=Determinations(
                    pure_seed=Percentage("98.4"),
                    germination_percent=96,
                    germination_tested_on=date(2024, 9, 28),
                    other_seed_report=report,
                ),
                issued_on=date(2024, 10, 2),
                signed_by="A. Pearce",
            )
        )

    def test_no_search_leaves_both_cells_empty(self, station) -> None:
        _, _, certificates = station
        self.issue(certificates, None)

        sheet = rows(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert sheet[0]["other seed searched g"] == ""
        assert sheet[0]["other seed found"] == ""

    def test_a_nil_return_fills_them_both(self, station) -> None:
        _, _, certificates = station
        self.issue(
            certificates,
            OtherSeedReport(kind="complete", weight_examined_g=Decimal("1200.0")),
        )

        sheet = rows(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert sheet[0]["other seed searched g"] == "1200.0"
        assert sheet[0]["other seed found"] == "none"

    def test_a_finding_is_carried_across(self, station) -> None:
        _, _, certificates = station
        self.issue(
            certificates,
            OtherSeedReport(
                kind="complete",
                weight_examined_g=Decimal("1200.0"),
                counts=(OtherSeedCount("Avena fatua", 4, Decimal("3.3")),),
            ),
        )

        sheet = rows(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert sheet[0]["other seed found"] == "Avena fatua 4"


class TestASpreadsheetCannotBeMadeToRunSomething:
    def test_a_species_name_that_starts_with_an_equals_sign_is_defused(self, station) -> None:
        # Nobody is going to send in a lot of =cmd|'/c calc'!A1, but the found
        # column is free text off a bench sheet and the register is opened in
        # Excel by an auditor.
        lots, searches, _ = station
        record(searches, findings=(Finding("=1+1", 3),))

        text = other_seed_register(lots, searches)

        assert "\n=1+1" not in text
        assert ",=1+1" not in text
