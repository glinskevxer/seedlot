"""The store list, as the person with the trolley reads it."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.reporting.registers import store_register
from arc.retention.model import DisposalReason, RetainedSample
from arc.storage.lots import LotRepository
from arc.storage.retention import RetentionRepository

BOOKED = date(2024, 12, 2)
TODAY = date(2024, 12, 27)


@pytest.fixture
def store(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    lots = LotRepository(connection)
    for serial in (41, 42, 43):
        lots.save(make_lot(serial=serial), booked_in_on=BOOKED)
    yield RetentionRepository(connection)
    connection.close()


def place(
    store,
    serial: int,
    *,
    held_from: date,
    kind: CertificateKind | None = CertificateKind.ORANGE_INTERNATIONAL,
    remaining: str = "860.0",
) -> None:
    store.place(
        RetainedSample(
            lot_reference=f"L-2024-{serial:04d}",
            species_name="Triticum aestivum",
            remaining_g=Decimal(remaining),
            held_from=held_from,
            certificate_kind=kind,
        )
    )


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


class TestWhatIsOnIt:
    def test_an_empty_store_is_a_header_and_nothing_else(self, store) -> None:
        assert rows(store_register(store, on=TODAY)) == []

    def test_a_held_jar_is_a_row(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))

        sheet = rows(store_register(store, on=TODAY))

        assert len(sheet) == 1
        assert sheet[0]["lot"] == "L-2024-0041"
        assert sheet[0]["remaining g"] == "860.0"

    def test_the_dates_are_both_there(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))

        sheet = rows(store_register(store, on=TODAY))

        assert sheet[0]["held from"] == "2024-12-18"
        assert sheet[0]["hold until"] == "2025-12-18"

    def test_the_days_left_are_counted_from_the_day_asked_about(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))

        sheet = rows(store_register(store, on=TODAY))

        assert sheet[0]["days left"] == "356"

    def test_the_certificate_kind_is_named(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))

        assert "orange" in rows(store_register(store, on=TODAY))[0]["certificate"]

    def test_a_jar_with_no_certificate_says_none(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18), kind=None)

        assert rows(store_register(store, on=TODAY))[0]["certificate"] == "none"

    def test_a_disposed_jar_is_not_on_it(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))
        store.dispose("L-2024-0041", on=date(2024, 12, 20), reason=DisposalReason.SPOILED)

        assert rows(store_register(store, on=TODAY)) == []


class TestTheOrderTheyComeIn:
    def test_the_nearest_to_its_date_is_first(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))
        place(store, 42, held_from=date(2024, 6, 1))
        place(store, 43, held_from=date(2024, 9, 4))

        sheet = rows(store_register(store, on=TODAY))

        assert [row["lot"] for row in sheet] == [
            "L-2024-0042",
            "L-2024-0043",
            "L-2024-0041",
        ]

    def test_a_shorter_period_can_put_a_newer_jar_first(self, store) -> None:
        # Held later, but a green report is only backed for half as long, so
        # it comes off the shelf first.
        place(store, 41, held_from=date(2024, 6, 1))
        place(
            store,
            42,
            held_from=date(2024, 9, 1),
            kind=CertificateKind.GREEN_ANALYSIS,
        )

        sheet = rows(store_register(store, on=TODAY))

        assert [row["lot"] for row in sheet] == ["L-2024-0042", "L-2024-0041"]


class TestTheDueColumn:
    def test_a_jar_inside_its_period_reads_no(self, store) -> None:
        place(store, 41, held_from=date(2024, 12, 18))

        assert rows(store_register(store, on=TODAY))[0]["due"] == "no"

    def test_one_past_it_reads_yes(self, store) -> None:
        place(store, 41, held_from=date(2023, 1, 4))

        assert rows(store_register(store, on=TODAY))[0]["due"] == "yes"

    def test_and_its_days_left_have_gone_negative(self, store) -> None:
        # Quoted, because a cell starting with a minus sign is a formula as
        # far as a spreadsheet is concerned and the writer defuses it. The
        # number a person reads is the same one either way.
        place(store, 41, held_from=date(2023, 1, 4))

        cell = rows(store_register(store, on=TODAY))[0]["days left"]

        assert cell == "'-358"
        assert int(cell.lstrip("'")) < 0

    def test_the_same_store_read_a_year_later(self, store) -> None:
        # Nothing about the store changed. The answer did, because the
        # question carries the day it is asked on.
        place(store, 41, held_from=date(2024, 12, 18))

        assert rows(store_register(store, on=TODAY))[0]["due"] == "no"
        assert rows(store_register(store, on=date(2025, 12, 19)))[0]["due"] == "yes"
