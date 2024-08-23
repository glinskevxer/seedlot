"""The registers the station has to be able to hand over."""

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
)
from arc.lots.model import LotStatus
from arc.quantities import Percentage
from arc.reporting.registers import certificate_register, merchant_register, work_in_progress
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository

BOOKED = date(2024, 9, 18)


@pytest.fixture
def station(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    yield LotRepository(connection), CertificateRepository(connection)
    connection.close()


def a_certificate(
    *,
    serial: int,
    lot_reference: str = "L-2024-0041",
    issued_on: date = date(2024, 10, 2),
    merchant: str = "Ravenscar Grain",
    withdrawn_on: date | None = None,
) -> Certificate:
    return Certificate(
        number=CertificateNumber("GB-0214", 2024, serial),
        kind=CertificateKind.ORANGE_INTERNATIONAL,
        lot_reference=lot_reference,
        species_name="Triticum aestivum",
        merchant=merchant,
        origin_country="GB",
        lot_weight_kg=Decimal("24000"),
        results=Determinations(
            pure_seed=Percentage("98.4"),
            other_seed=Percentage("0.8"),
            inert_matter=Percentage("0.8"),
            germination_percent=96,
            germination_tested_on=date(2024, 9, 28),
        ),
        issued_on=issued_on,
        signed_by="A. Pearce",
        withdrawn_on=withdrawn_on,
    )


def read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


class TestTheCertificateRegister:
    def test_an_empty_month_is_a_header_and_nothing_else(self, station) -> None:
        _, certificates = station

        sheet = certificate_register(
            certificates, start=date(2024, 10, 1), end=date(2024, 10, 31)
        )

        assert read_csv(sheet) == []
        assert sheet.startswith('"number"')

    def test_it_carries_the_figures_that_were_reported(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=187))

        rows = read_csv(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert len(rows) == 1
        assert rows[0]["number"] == "GB-0214/2024/00187"
        assert rows[0]["pure seed"] == "98.4"
        assert rows[0]["germination"] == "96"
        assert rows[0]["germination tested"] == "2024-09-28"

    def test_it_only_covers_the_dates_it_was_asked_for(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=1, issued_on=date(2024, 9, 30)))
        certificates.issue(a_certificate(serial=2, issued_on=date(2024, 10, 2)))
        certificates.issue(a_certificate(serial=3, issued_on=date(2024, 11, 1)))

        rows = read_csv(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert [row["number"] for row in rows] == ["GB-0214/2024/00002"]

    def test_a_withdrawn_certificate_is_still_on_the_register(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=187))
        certificates.withdraw("GB-0214/2024/00187", on=date(2024, 11, 1))

        rows = read_csv(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert rows[0]["withdrawn on"] == "2024-11-01"

    def test_a_merchant_name_with_a_comma_stays_one_column(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=187, merchant="Ravenscar Grain, Whitby"))

        rows = read_csv(
            certificate_register(certificates, start=date(2024, 10, 1), end=date(2024, 10, 31))
        )

        assert rows[0]["merchant"] == "Ravenscar Grain, Whitby"


class TestTheMondayList:
    def test_an_empty_station_has_no_work(self, station) -> None:
        lots, certificates = station

        assert work_in_progress(lots, certificates) == ()

    def test_it_leaves_closed_lots_out(self, station) -> None:
        lots, certificates = station
        open_lot = make_lot(serial=41)
        closed = make_lot(serial=42)
        closed.move_to(LotStatus.CLOSED)
        lots.save(open_lot, booked_in_on=BOOKED)
        lots.save(closed, booked_in_on=BOOKED)

        items = work_in_progress(lots, certificates)

        assert [str(item.lot.reference) for item in items] == ["L-2024-0041"]

    def test_it_says_how_many_certificates_a_lot_has(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=187))

        items = work_in_progress(lots, certificates)

        assert items[0].certificates_issued == 1

    def test_it_flags_what_is_actually_on_the_bench(self, station) -> None:
        lots, certificates = station
        waiting = make_lot(serial=41)
        working = make_lot(serial=42)
        working.move_to(LotStatus.SAMPLED)
        lots.save(waiting, booked_in_on=BOOKED)
        lots.save(working, booked_in_on=BOOKED)

        items = {str(item.lot.reference): item for item in work_in_progress(lots, certificates)}

        assert not items["L-2024-0041"].is_waiting_on_the_bench
        assert items["L-2024-0042"].is_waiting_on_the_bench


class TestOneMerchant:
    def test_only_that_merchants_lots_come_back(self, station) -> None:
        lots, certificates = station
        mine = make_lot(serial=41)
        theirs = make_lot(serial=42)
        theirs.merchant = "Scarborough Seeds"
        lots.save(mine, booked_in_on=BOOKED)
        lots.save(theirs, booked_in_on=BOOKED)

        found = merchant_register(lots, certificates, "Ravenscar Grain")

        assert [str(lot.reference) for lot, _ in found] == ["L-2024-0041"]

    def test_the_name_is_matched_however_it_was_typed(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)

        found = merchant_register(lots, certificates, "  ravenscar GRAIN ")

        assert len(found) == 1

    def test_the_certificates_come_with_the_lot(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)
        certificates.issue(a_certificate(serial=187))

        (_, issued), = merchant_register(lots, certificates, "Ravenscar Grain")

        assert [str(c.number) for c in issued] == ["GB-0214/2024/00187"]

    def test_a_merchant_nobody_has_heard_of_has_nothing(self, station) -> None:
        lots, certificates = station
        lots.save(make_lot(), booked_in_on=BOOKED)

        assert merchant_register(lots, certificates, "Nobody Ltd") == ()
