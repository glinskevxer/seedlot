"""Searches for other species, round tripped through SQLite.

The findings are the part worth testing hard. They go in a second table, they
come back joined, and a search that lost them on the way reads as a clean lot,
which is the one failure a buyer would act on without questioning it.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository

BOOKED = date(2024, 9, 18)
SEARCHED = date(2024, 9, 26)
LOT = "L-2024-0041"


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def searches(db) -> OtherSeedRepository:
    return OtherSeedRepository(db)


def a_search(
    *,
    kind: SearchKind = SearchKind.COMPLETE,
    weight: str = "1200",
    findings: tuple[Finding, ...] = (),
    sought: tuple[str, ...] = (),
    analyst: str = "J. Whitfield",
) -> OtherSeedSearch:
    return OtherSeedSearch(
        species_name="Triticum aestivum",
        kind=kind,
        weight_examined_g=Decimal(weight),
        findings=findings,
        sought=sought,
        analyst=analyst,
    )


class TestRoundTrip:
    def test_a_nil_return_comes_back_as_a_nil_return(self, searches) -> None:
        searches.record(LOT, a_search(), searched_on=SEARCHED)

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.search.nil_return is True
        assert stored.searched_on == SEARCHED

    def test_the_findings_come_back_with_the_search(self, searches) -> None:
        searches.record(
            LOT,
            a_search(findings=(Finding("Avena fatua", 4), Finding("Galium aparine", 2))),
            searched_on=SEARCHED,
        )

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.search.count_of("Avena fatua") == 4
        assert stored.search.count_of("Galium aparine") == 2
        assert stored.search.total_found == 6

    def test_the_weight_examined_keeps_the_places_it_was_typed_with(self, searches) -> None:
        searches.record(LOT, a_search(weight="1200.0"), searched_on=SEARCHED)

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.search.weight_examined_g == Decimal("1200.0")
        assert str(stored.search.weight_examined_g) == "1200.0"

    def test_the_kind_survives(self, searches) -> None:
        searches.record(
            LOT,
            a_search(kind=SearchKind.REDUCED, weight="240", sought=("Avena fatua",)),
            searched_on=SEARCHED,
        )

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.kind is SearchKind.REDUCED

    def test_the_sought_list_survives_with_more_than_one_name(self, searches) -> None:
        searches.record(
            LOT,
            a_search(
                kind=SearchKind.LIMITED,
                sought=("Avena fatua", "Galium aparine", "Bromus secalinus"),
            ),
            searched_on=SEARCHED,
        )

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.search.sought == (
            "Avena fatua",
            "Galium aparine",
            "Bromus secalinus",
        )

    def test_an_empty_sought_list_comes_back_empty_rather_than_as_one_blank(
        self, searches
    ) -> None:
        # Splitting an empty string gives a list with one empty item in it,
        # which would read as a search looking for a species with no name.
        searches.record(LOT, a_search(), searched_on=SEARCHED)

        stored = searches.latest_for_lot(LOT)

        assert stored is not None
        assert stored.search.sought == ()

    def test_the_row_id_comes_back_from_recording(self, searches) -> None:
        first = searches.record(LOT, a_search(), searched_on=SEARCHED)
        second = searches.record(LOT, a_search(), searched_on=SEARCHED)

        assert second > first


class TestMoreThanOneSearch:
    def test_they_come_back_oldest_first(self, searches) -> None:
        searches.record(
            LOT, a_search(findings=(Finding("Avena fatua", 4),)), searched_on=SEARCHED
        )
        searches.record(
            LOT,
            a_search(findings=(Finding("Avena fatua", 7),)),
            searched_on=date(2024, 10, 1),
        )

        found = searches.for_lot(LOT)

        assert [stored.search.count_of("Avena fatua") for stored in found] == [4, 7]

    def test_recording_a_second_one_does_not_overwrite_the_first(self, searches) -> None:
        searches.record(LOT, a_search(), searched_on=SEARCHED)
        searches.record(LOT, a_search(), searched_on=SEARCHED)

        assert len(searches.for_lot(LOT)) == 2

    def test_counts_of_one_species_across_searches(self, searches) -> None:
        searches.record(
            LOT, a_search(findings=(Finding("Avena fatua", 4),)), searched_on=SEARCHED
        )
        searches.record(
            LOT, a_search(findings=(Finding("Avena fatua", 7),)), searched_on=SEARCHED
        )

        assert searches.counts_of(LOT, "Avena fatua") == (4, 7)

    def test_a_complete_search_that_found_none_counts_as_a_zero(self, searches) -> None:
        # It looked and did not find any, which is a count of nothing and not
        # an absence of evidence.
        searches.record(LOT, a_search(), searched_on=SEARCHED)
        searches.record(
            LOT, a_search(findings=(Finding("Avena fatua", 3),)), searched_on=SEARCHED
        )

        assert searches.counts_of(LOT, "Avena fatua") == (0, 3)

    def test_a_limited_search_that_was_not_looking_for_it_is_left_out(self, searches) -> None:
        # This one is the point of the method. A search for cleavers says
        # nothing at all about wild oats, and folding its zero into the
        # comparison would invent an agreement that nobody measured.
        searches.record(
            LOT,
            a_search(kind=SearchKind.LIMITED, sought=("Galium aparine",)),
            searched_on=SEARCHED,
        )
        searches.record(
            LOT, a_search(findings=(Finding("Avena fatua", 3),)), searched_on=SEARCHED
        )

        assert searches.counts_of(LOT, "Avena fatua") == (3,)

    def test_nothing_recorded_gives_nothing_back(self, searches) -> None:
        assert searches.for_lot(LOT) == ()
        assert searches.latest_for_lot(LOT) is None
        assert searches.counts_of(LOT, "Avena fatua") == ()


class TestWhatTheDatabaseRefuses:
    def test_a_search_against_a_lot_that_does_not_exist(self, searches) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            searches.record("L-2024-9999", a_search(), searched_on=SEARCHED)

    def test_the_same_species_twice_in_one_search(self, searches) -> None:
        # The rules refuse this before it gets here. The constraint is the
        # second line of defence, for the day something writes directly.
        with pytest.raises(sqlite3.IntegrityError):
            searches.record(
                LOT,
                a_search(findings=(Finding("Avena fatua", 4), Finding("Avena fatua", 1))),
                searched_on=SEARCHED,
            )

    def test_and_the_failed_search_left_nothing_behind(self, searches) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            searches.record(
                LOT,
                a_search(findings=(Finding("Avena fatua", 4), Finding("Avena fatua", 1))),
                searched_on=SEARCHED,
            )

        assert searches.for_lot(LOT) == ()

    def test_an_unknown_kind_cannot_be_written(self, db) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into other_seed_search
                    (lot_reference, species_name, kind, weight_examined_g,
                     sought, analyst, searched_on)
                values (?, 'Triticum aestivum', 'quick', '1200', '', 'J. W', '2024-09-26')
                """,
                (LOT,),
            )

    def test_a_negative_count_cannot_be_written(self, db, searches) -> None:
        search_id = searches.record(LOT, a_search(), searched_on=SEARCHED)

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "insert into other_seed_finding (search_id, species_name, count) "
                "values (?, 'Avena fatua', -1)",
                (search_id,),
            )
