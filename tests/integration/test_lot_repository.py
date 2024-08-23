"""Lots, round tripped through the database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.errors import NotFound
from arc.lots.model import ContainerKind, LotReference, LotStatus
from arc.storage.lots import LotRepository


@pytest.fixture
def lots(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    yield LotRepository(connection)
    connection.close()


BOOKED = date(2024, 9, 18)


class TestRoundTripping:
    def test_a_lot_comes_back_as_it_went_in(self, lots) -> None:
        original = make_lot()

        lots.save(original, booked_in_on=BOOKED)
        found = lots.require("L-2024-0041")

        assert found == original

    def test_the_weight_keeps_every_decimal_place_it_was_written_to(self, lots) -> None:
        lots.save(make_lot(weight_kg="24000.50"), booked_in_on=BOOKED)

        found = lots.require("L-2024-0041")

        assert found.declared_weight_kg == Decimal("24000.50")
        assert str(found.declared_weight_kg) == "24000.50"

    def test_the_container_kind_and_status_come_back_as_themselves(self, lots) -> None:
        lot = make_lot(container_kind=ContainerKind.BULK, container_count=0)
        lot.move_to(LotStatus.SAMPLED)

        lots.save(lot, booked_in_on=BOOKED)
        found = lots.require("L-2024-0041")

        assert found.container_kind is ContainerKind.BULK
        assert found.status is LotStatus.SAMPLED

    def test_the_dates_come_back_as_dates(self, lots) -> None:
        lots.save(make_lot(), booked_in_on=BOOKED)

        assert lots.require("L-2024-0041").sealed_on == date(2024, 9, 12)

    def test_a_reference_object_and_its_text_find_the_same_lot(self, lots) -> None:
        lots.save(make_lot(), booked_in_on=BOOKED)

        by_object = lots.require(LotReference(2024, 41))
        by_text = lots.require("L-2024-0041")

        assert by_object == by_text


class TestLookingThingsUp:
    def test_a_lot_nobody_booked_in_is_not_found(self, lots) -> None:
        assert lots.find("L-2024-9999") is None

    def test_requiring_one_that_is_missing_says_what_was_asked_for(self, lots) -> None:
        with pytest.raises(NotFound) as caught:
            lots.require("L-2024-9999")

        assert "L-2024-9999" in str(caught.value)

    def test_saving_the_same_reference_twice_updates_rather_than_duplicates(
        self, lots
    ) -> None:
        lot = make_lot()
        lots.save(lot, booked_in_on=BOOKED)

        lot.move_to(LotStatus.SAMPLED)
        lots.save(lot, booked_in_on=BOOKED)

        assert lots.count() == 1
        assert lots.require("L-2024-0041").status is LotStatus.SAMPLED

    def test_the_work_queue_leaves_closed_lots_out(self, lots) -> None:
        open_lot = make_lot(serial=41)
        closed_lot = make_lot(serial=42)
        closed_lot.move_to(LotStatus.CLOSED)

        lots.save(open_lot, booked_in_on=BOOKED)
        lots.save(closed_lot, booked_in_on=BOOKED)

        assert [str(lot.reference) for lot in lots.open_lots()] == ["L-2024-0041"]

    def test_the_queue_is_oldest_first(self, lots) -> None:
        lots.save(make_lot(serial=90), booked_in_on=date(2024, 9, 1))
        lots.save(make_lot(serial=12), booked_in_on=date(2024, 9, 20))
        lots.save(make_lot(serial=55), booked_in_on=date(2024, 9, 10))

        assert [str(lot.reference) for lot in lots.open_lots()] == [
            "L-2024-0090",
            "L-2024-0055",
            "L-2024-0012",
        ]

    def test_lots_can_be_pulled_out_by_species(self, lots) -> None:
        lots.save(make_lot(serial=41), booked_in_on=BOOKED)
        lots.save(
            make_lot(serial=77, species_name="Lolium perenne", weight_kg="8000"),
            booked_in_on=BOOKED,
        )

        found = lots.for_species("Lolium perenne")

        assert [str(lot.reference) for lot in found] == ["L-2024-0077"]


class TestSublots:
    def test_a_sublot_remembers_what_it_came_out_of(self, lots) -> None:
        parent = make_lot(serial=41, weight_kg="60000")
        lots.save(parent, booked_in_on=BOOKED)

        first = make_lot(serial=42, weight_kg="30000")
        first.sublot_of = parent.reference
        second = make_lot(serial=43, weight_kg="30000")
        second.sublot_of = parent.reference
        lots.save(first, booked_in_on=BOOKED)
        lots.save(second, booked_in_on=BOOKED)

        found = lots.sublots_of("L-2024-0041")

        assert [str(lot.reference) for lot in found] == ["L-2024-0042", "L-2024-0043"]
        assert all(lot.is_sublot for lot in found)

    def test_an_ordinary_lot_has_no_sublots(self, lots) -> None:
        lots.save(make_lot(), booked_in_on=BOOKED)

        assert lots.sublots_of("L-2024-0041") == ()

    def test_a_sublot_of_a_lot_that_does_not_exist_is_refused_by_the_database(
        self, lots
    ) -> None:
        import sqlite3

        orphan = make_lot(serial=42)
        orphan.sublot_of = LotReference(2024, 999)

        with pytest.raises(sqlite3.IntegrityError):
            lots.save(orphan, booked_in_on=BOOKED)
