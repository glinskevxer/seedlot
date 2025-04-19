"""Counting the year's work.

Certificates rather than tests throughout. A lot tested three times and
certified once is one job, and the tests that matter most here are the ones
where those two counts would differ.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
)
from arc.germination.model import Treatment
from arc.quantities import Percentage
from arc.reporting.statistics import by_month, by_species, kinds_issued, turnaround
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository

YEAR_START = date(2024, 1, 1)
YEAR_END = date(2024, 12, 31)


@pytest.fixture
def station(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    yield LotRepository(connection), CertificateRepository(connection)
    connection.close()


def book(lots, serial: int, *, on: date = date(2024, 9, 18)) -> str:
    lot = make_lot(serial=serial)
    lots.save(lot, booked_in_on=on)
    return str(lot.reference)


def certify(
    certificates,
    *,
    serial: int,
    lot_reference: str,
    issued_on: date,
    species: str = "Triticum aestivum",
    germination: int | None = 96,
    kind: CertificateKind = CertificateKind.ORANGE_INTERNATIONAL,
) -> str:
    number = CertificateNumber("GB-0214", issued_on.year, serial)
    certificates.issue(
        Certificate(
            number=number,
            kind=kind,
            lot_reference=lot_reference,
            species_name=species,
            merchant="Ravenscar Grain",
            origin_country="GB",
            lot_weight_kg=Decimal("24000"),
            results=Determinations(
                pure_seed=Percentage("98.4"),
                germination_percent=germination,
                germination_tested_on=None if germination is None else issued_on,
                germination_treatment=None if germination is None else Treatment.NONE,
            ),
            issued_on=issued_on,
            signed_by="A. Pearce",
        )
    )
    return str(number)


class TestByMonth:
    def test_a_year_with_nothing_in_it(self, station) -> None:
        _, certificates = station

        months = by_month(certificates, start=YEAR_START, end=YEAR_END)

        assert len(months) == 12
        assert all(month.issued == 0 for month in months)

    def test_an_empty_month_is_a_row_of_zeroes_not_a_missing_row(self, station) -> None:
        lots, certificates = station
        reference = book(lots, 41)
        certify(certificates, serial=1, lot_reference=reference, issued_on=date(2024, 3, 4))

        months = by_month(certificates, start=date(2024, 1, 1), end=date(2024, 4, 30))

        assert [month.label for month in months] == [
            "2024-01",
            "2024-02",
            "2024-03",
            "2024-04",
        ]
        assert [month.issued for month in months] == [0, 0, 1, 0]

    def test_certificates_land_in_the_month_they_were_issued(self, station) -> None:
        lots, certificates = station
        first = book(lots, 41)
        second = book(lots, 42)
        certify(certificates, serial=1, lot_reference=first, issued_on=date(2024, 3, 4))
        certify(certificates, serial=2, lot_reference=second, issued_on=date(2024, 3, 28))

        months = by_month(certificates, start=date(2024, 3, 1), end=date(2024, 3, 31))

        assert months[0].issued == 2

    def test_a_withdrawn_certificate_is_counted_both_ways(self, station) -> None:
        lots, certificates = station
        reference = book(lots, 41)
        number = certify(
            certificates, serial=1, lot_reference=reference, issued_on=date(2024, 3, 4)
        )
        certificates.withdraw(number, on=date(2024, 4, 1))

        months = by_month(certificates, start=date(2024, 3, 1), end=date(2024, 3, 31))

        assert months[0].issued == 1
        assert months[0].withdrawn == 1
        assert months[0].stood == 0

    def test_a_range_that_crosses_a_year(self, station) -> None:
        _, certificates = station

        months = by_month(certificates, start=date(2024, 11, 1), end=date(2025, 2, 28))

        assert [month.label for month in months] == [
            "2024-11",
            "2024-12",
            "2025-01",
            "2025-02",
        ]

    def test_a_single_month(self, station) -> None:
        _, certificates = station

        months = by_month(certificates, start=date(2024, 3, 1), end=date(2024, 3, 31))

        assert len(months) == 1


class TestBySpecies:
    def test_the_busiest_species_is_first(self, station) -> None:
        lots, certificates = station
        for serial in (41, 42, 43):
            reference = book(lots, serial)
            species = "Hordeum vulgare" if serial == 43 else "Triticum aestivum"
            certify(
                certificates,
                serial=serial,
                lot_reference=reference,
                issued_on=date(2024, 3, 4),
                species=species,
            )

        summaries = by_species(certificates, start=YEAR_START, end=YEAR_END)

        assert summaries[0].species_name == "Triticum aestivum"
        assert summaries[0].certificates == 2

    def test_the_mean_germination_is_over_the_ones_that_have_one(self, station) -> None:
        # Two certificates with germinations and one purity only. The mean is
        # over the two, not over the three.
        lots, certificates = station
        for serial, germination in ((41, 90), (42, 96), (43, None)):
            reference = book(lots, serial)
            certify(
                certificates,
                serial=serial,
                lot_reference=reference,
                issued_on=date(2024, 3, 4),
                germination=germination,
            )

        summary = by_species(certificates, start=YEAR_START, end=YEAR_END)[0]

        assert summary.certificates == 3
        assert summary.mean_germination == 93

    def test_the_lowest_is_kept_too(self, station) -> None:
        lots, certificates = station
        for serial, germination in ((41, 90), (42, 96)):
            reference = book(lots, serial)
            certify(
                certificates,
                serial=serial,
                lot_reference=reference,
                issued_on=date(2024, 3, 4),
                germination=germination,
            )

        summary = by_species(certificates, start=YEAR_START, end=YEAR_END)[0]

        assert summary.lowest_germination == 90

    def test_a_species_with_no_germinations_at_all(self, station) -> None:
        lots, certificates = station
        reference = book(lots, 41)
        certify(
            certificates,
            serial=1,
            lot_reference=reference,
            issued_on=date(2024, 3, 4),
            germination=None,
        )

        summary = by_species(certificates, start=YEAR_START, end=YEAR_END)[0]

        assert summary.had_germinations is False
        assert summary.mean_germination is None

    def test_nothing_issued_gives_nothing_back(self, station) -> None:
        _, certificates = station

        assert by_species(certificates, start=YEAR_START, end=YEAR_END) == ()


class TestTurnaround:
    def test_days_from_booking_in_to_issuing(self, station) -> None:
        lots, certificates = station
        reference = book(lots, 41, on=date(2024, 9, 18))
        certify(certificates, serial=1, lot_reference=reference, issued_on=date(2024, 10, 2))

        took = turnaround(lots, certificates, start=YEAR_START, end=YEAR_END)

        assert took is not None
        assert took.jobs == 1
        assert took.fastest == 14
        assert took.slowest == 14

    def test_the_median_of_three(self, station) -> None:
        lots, certificates = station
        for serial, days in ((41, 10), (42, 14), (43, 30)):
            reference = book(lots, serial, on=date(2024, 9, 1))
            certify(
                certificates,
                serial=serial,
                lot_reference=reference,
                issued_on=date(2024, 9, 1) + timedelta(days=days),
            )

        took = turnaround(lots, certificates, start=YEAR_START, end=YEAR_END)

        assert took is not None
        assert took.median == 14
        assert took.fastest == 10
        assert took.slowest == 30

    def test_a_reissue_does_not_start_the_clock_again(self, station) -> None:
        # The second certificate on the same lot is a correction, not a job.
        lots, certificates = station
        reference = book(lots, 41, on=date(2024, 9, 18))
        certify(certificates, serial=1, lot_reference=reference, issued_on=date(2024, 10, 2))
        certify(certificates, serial=2, lot_reference=reference, issued_on=date(2024, 11, 30))

        took = turnaround(lots, certificates, start=YEAR_START, end=YEAR_END)

        assert took is not None
        assert took.jobs == 1
        assert took.slowest == 14

    def test_nothing_issued_gives_nothing_back(self, station) -> None:
        lots, certificates = station

        assert turnaround(lots, certificates, start=YEAR_START, end=YEAR_END) is None

    def test_it_describes_itself_in_one_line(self, station) -> None:
        lots, certificates = station
        reference = book(lots, 41, on=date(2024, 9, 18))
        certify(certificates, serial=1, lot_reference=reference, issued_on=date(2024, 10, 2))

        took = turnaround(lots, certificates, start=YEAR_START, end=YEAR_END)

        assert took is not None
        assert took.describe() == "1 jobs, 14 to 14 days, median 14"


class TestKindsIssued:
    def test_each_kind_is_counted(self, station) -> None:
        lots, certificates = station
        for serial, kind in (
            (41, CertificateKind.ORANGE_INTERNATIONAL),
            (42, CertificateKind.ORANGE_INTERNATIONAL),
            (43, CertificateKind.GREEN_ANALYSIS),
        ):
            reference = book(lots, serial)
            certify(
                certificates,
                serial=serial,
                lot_reference=reference,
                issued_on=date(2024, 3, 4),
                kind=kind,
            )

        counts = kinds_issued(certificates, start=YEAR_START, end=YEAR_END)

        assert counts[CertificateKind.ORANGE_INTERNATIONAL] == 2
        assert counts[CertificateKind.GREEN_ANALYSIS] == 1

    def test_a_kind_nobody_issued_is_absent(self, station) -> None:
        _, certificates = station

        assert kinds_issued(certificates, start=YEAR_START, end=YEAR_END) == {}
