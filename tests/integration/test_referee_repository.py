"""Comparisons against another laboratory, round tripped.

The verdict is stored rather than recomputed on the way out, and one of these
tests is about exactly that: a comparison written down under one allowance has
to keep reading the same way even if the number the code would work out today
is different.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.referee.between_labs import (
    Referee,
    RefereeVerdict,
    compare_germination,
    compare_purity,
)
from arc.retention.model import Determination
from arc.storage.lots import LotRepository
from arc.storage.referee import RefereeRepository

BOOKED = date(2024, 12, 2)
COMPARED = date(2025, 1, 8)
LOT = "L-2024-0041"
NUMBER = "GB-0214/2024/00187"


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def referee(db) -> RefereeRepository:
    return RefereeRepository(db)


def record(
    referee,
    comparison: Referee,
    *,
    determination: Determination = Determination.GERMINATION,
    number: str = NUMBER,
    laboratory: str = "NL-0510 Wageningen",
    raised_by: str = "Ravenscar Grain",
    on: date = COMPARED,
) -> int:
    return referee.record(
        LOT,
        number,
        determination,
        comparison,
        other_laboratory=laboratory,
        raised_by=raised_by,
        on=on,
    )


class TestRoundTrip:
    def test_a_germination_that_agreed(self, referee) -> None:
        record(referee, compare_germination(96, 94))

        stored = referee.for_lot(LOT)[0]

        assert stored.determination is Determination.GERMINATION
        assert stored.referee.ours == Decimal("96")
        assert stored.referee.theirs == Decimal("94")
        assert stored.stands is True

    def test_one_that_did_not(self, referee) -> None:
        record(referee, compare_germination(96, 80))

        stored = referee.for_lot(LOT)[0]

        assert stored.stands is False
        assert stored.referee.verdict is RefereeVerdict.REFER

    def test_a_purity_comparison(self, referee) -> None:
        record(
            referee,
            compare_purity(Decimal("98.4"), Decimal("98.2"), chaffy=False),
            determination=Determination.PURITY,
        )

        stored = referee.for_lot(LOT)[0]

        assert stored.determination is Determination.PURITY
        assert stored.referee.ours == Decimal("98.4")

    def test_the_allowance_is_kept_as_it_was(self, referee) -> None:
        made = compare_germination(96, 94)
        record(referee, made)

        assert referee.for_lot(LOT)[0].referee.allowance == made.allowance

    def test_who_asked_and_who_did_it_are_both_kept(self, referee) -> None:
        record(referee, compare_germination(96, 94))

        stored = referee.for_lot(LOT)[0]

        assert stored.other_laboratory == "NL-0510 Wageningen"
        assert stored.raised_by == "Ravenscar Grain"
        assert stored.compared_on == COMPARED

    def test_the_certificate_it_challenges_is_kept(self, referee) -> None:
        record(referee, compare_germination(96, 94))

        assert referee.for_lot(LOT)[0].certificate_number == NUMBER


class TestAnOldComparisonKeepsItsVerdict:
    def test_a_stored_agreement_does_not_get_recomputed(self, db, referee) -> None:
        # Written down as an agreement with a wide allowance. If anything read
        # the numbers back and worked the verdict out again with a narrower
        # table, this would flip, and a merchant would be told the station
        # changed its mind about a comparison made a year ago.
        db.execute(
            """
            insert into referee_comparison
                (lot_reference, certificate_number, determination, ours, theirs,
                 allowance, verdict, other_laboratory, raised_by, compared_on)
            values (?, ?, 'germination', '96', '80', '20', 'agree',
                    'NL-0510 Wageningen', 'Ravenscar Grain', '2025-01-08')
            """,
            (LOT, NUMBER),
        )

        stored = referee.for_lot(LOT)[0]

        assert stored.stands is True
        assert compare_germination(96, 80).verdict is RefereeVerdict.REFER


class TestFindingThem:
    def test_they_come_back_in_the_order_they_were_made(self, referee) -> None:
        record(referee, compare_germination(96, 94))
        record(referee, compare_germination(96, 80), on=date(2025, 2, 3))

        assert [stored.stands for stored in referee.for_lot(LOT)] == [True, False]

    def test_by_certificate(self, referee) -> None:
        record(referee, compare_germination(96, 94))
        record(referee, compare_germination(96, 92), number="GB-0214/2024/00188")

        found = referee.for_certificate(NUMBER)

        assert len(found) == 1
        assert found[0].referee.theirs == Decimal("94")

    def test_the_disputed_ones_on_their_own(self, referee) -> None:
        record(referee, compare_germination(96, 94))
        record(referee, compare_germination(96, 80), on=date(2025, 2, 3))

        disputed = referee.disputed()

        assert len(disputed) == 1
        assert disputed[0].referee.theirs == Decimal("80")

    def test_disputed_comes_back_newest_first(self, referee) -> None:
        record(referee, compare_germination(96, 78), on=date(2025, 1, 8))
        record(referee, compare_germination(96, 80), on=date(2025, 3, 3))

        assert [stored.compared_on for stored in referee.disputed()] == [
            date(2025, 3, 3),
            date(2025, 1, 8),
        ]

    def test_a_lot_nobody_disputed(self, referee) -> None:
        assert referee.for_lot(LOT) == ()
        assert referee.disputed() == ()


class TestWhatWillNotBeWritten:
    def test_moisture_is_not_refereed_this_way(self, referee) -> None:
        with pytest.raises(ValueError, match="not refereed"):
            record(
                referee,
                compare_germination(96, 94),
                determination=Determination.MOISTURE,
            )

    def test_a_comparison_against_a_lot_that_does_not_exist(self, referee) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            referee.record(
                "L-2024-9999",
                NUMBER,
                Determination.GERMINATION,
                compare_germination(96, 94),
                other_laboratory="NL-0510 Wageningen",
                raised_by="Ravenscar Grain",
                on=COMPARED,
            )

    def test_a_verdict_the_database_does_not_know(self, db) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into referee_comparison
                    (lot_reference, certificate_number, determination, ours, theirs,
                     allowance, verdict, other_laboratory, raised_by, compared_on)
                values (?, ?, 'germination', '96', '94', '5', 'probably',
                        'NL-0510', 'Ravenscar Grain', '2025-01-08')
                """,
                (LOT, NUMBER),
            )

    def test_a_determination_that_is_not_refereed(self, db) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into referee_comparison
                    (lot_reference, certificate_number, determination, ours, theirs,
                     allowance, verdict, other_laboratory, raised_by, compared_on)
                values (?, ?, 'moisture', '14.0', '14.2', '0.5', 'agree',
                        'NL-0510', 'Ravenscar Grain', '2025-01-08')
                """,
                (LOT, NUMBER),
            )
