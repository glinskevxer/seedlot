"""The day book itself, rather than the commands that write to it.

Three of these cover the parts the console does not reach: reading a day's
entries back, counting them, and the rollback that has to leave the book alone
when something else in the same transaction fails.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.retention.model import Determination, RetainedSample
from arc.storage.journal import Entry, Journal
from arc.storage.lots import LotRepository
from arc.storage.retention import RetentionRepository

MONDAY = datetime(2025, 4, 7, 9, 15, 0)
TUESDAY = datetime(2025, 4, 8, 14, 30, 0)


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=date(2025, 4, 7))
    yield connection
    connection.close()


@pytest.fixture
def book(db) -> Journal:
    return Journal(db)


def write(book, at: datetime, action: str = "booked in", operator: str = "jwhitfield"):
    return book.record(operator, action, "L-2024-0041", at=at, detail="")


class TestOneEntry:
    def test_the_date_comes_off_the_timestamp(self) -> None:
        entry = Entry(at=MONDAY, operator="jwhitfield", action="booked in", subject="L")

        assert entry.on == date(2025, 4, 7)

    def test_it_prints_without_a_detail(self) -> None:
        entry = Entry(at=MONDAY, operator="jwhitfield", action="booked in", subject="L")

        assert entry.describe() == "2025-04-07 09:15:00 jwhitfield booked in L"

    def test_and_with_one(self) -> None:
        entry = Entry(
            at=MONDAY,
            operator="jwhitfield",
            action="booked in",
            subject="L",
            detail="24000 kg",
        )

        assert entry.describe().endswith("booked in L: 24000 kg")


class TestADaysWork:
    def test_the_entries_for_one_day(self, book) -> None:
        write(book, MONDAY)
        write(book, TUESDAY, action="recorded a purity for")

        monday = book.on_day(date(2025, 4, 7))

        assert len(monday) == 1
        assert monday[0].action == "booked in"

    def test_a_day_with_nothing_on_it(self, book) -> None:
        write(book, MONDAY)

        assert book.on_day(date(2025, 4, 9)) == ()

    def test_they_come_back_in_the_order_they_happened(self, book) -> None:
        write(book, datetime(2025, 4, 7, 16, 0, 0), action="second")
        write(book, datetime(2025, 4, 7, 9, 0, 0), action="first")

        assert [entry.action for entry in book.on_day(date(2025, 4, 7))] == [
            "first",
            "second",
        ]

    def test_counting_the_whole_book(self, book) -> None:
        assert book.count() == 0

        write(book, MONDAY)
        write(book, TUESDAY)

        assert book.count() == 2


class TestTheBookAndTheRestOfTheDatabase:
    def test_a_failed_transaction_leaves_the_book_alone(self, db, book) -> None:
        # The store's draw opens a transaction. If the second half of it
        # fails, the weight must not have moved, and neither must anything
        # else written inside the same transaction.
        store = RetentionRepository(db)
        store.place(
            RetainedSample(
                lot_reference="L-2024-0041",
                species_name="Triticum aestivum",
                remaining_g=Decimal("100.0"),
                held_from=date(2025, 4, 7),
            )
        )

        with pytest.raises(ValueError):
            store.draw(
                "L-2024-0041",
                Determination.PURITY,
                Decimal("500.0"),
                on=date(2025, 4, 8),
                analyst="R. Naylor",
            )

        assert store.require("L-2024-0041").remaining_g == Decimal("100.0")
        assert store.draws_for("L-2024-0041") == ()

    def test_an_entry_about_something_that_no_longer_exists(self, book, db) -> None:
        # No foreign key on purpose. An audit trail that a delete elsewhere
        # can break is not one.
        book.record(
            "jwhitfield",
            "booked in",
            "L-1999-0001",
            at=MONDAY,
            detail="a lot from before this database",
        )

        assert len(book.for_subject("L-1999-0001")) == 1

    def test_the_book_survives_the_lot_being_removed(self, book, db) -> None:
        write(book, MONDAY)
        db.execute("delete from lot where reference = ?", ("L-2024-0041",))

        assert len(book.for_subject("L-2024-0041")) == 1
