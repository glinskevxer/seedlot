"""The treatment, stored against the test it was applied to.

Migration six adds the column to a table that already has rows in it. Anything
recorded before the station started tracking treatments was a test with nothing
done to the sample, so the default carries the right meaning rather than a
placeholder, and one of these tests says so by migrating a database that
already holds a test.
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.germination.dormancy import check_treatment
from arc.germination.model import GerminationTest, Replicate, Treatment
from arc.species import register
from arc.storage.determinations import GerminationRepository
from arc.storage.lots import LotRepository
from arc.storage.schema import MIGRATIONS, applied_versions, connect, migrate

BOOKED = date(2024, 11, 4)
LOT = "L-2024-0041"


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def germination(db) -> GerminationRepository:
    return GerminationRepository(db)


def a_test(
    *,
    normal: int = 96,
    fresh: int = 0,
    treatment: Treatment = Treatment.NONE,
    is_retest: bool = False,
) -> GerminationTest:
    return GerminationTest(
        lot_reference=LOT,
        species_name="Triticum aestivum",
        replicates=tuple(
            Replicate(normal=normal, abnormal=100 - normal - fresh, hard=0, fresh=fresh, dead=0)
            for _ in range(4)
        ),
        seeds_per_replicate=100,
        set_down_on=date(2024, 11, 5),
        final_count_on=date(2024, 11, 13),
        analyst="J. Whitfield",
        is_retest=is_retest,
        treatment=treatment,
    )


class TestRoundTrip:
    def test_an_untreated_test_comes_back_untreated(self, germination) -> None:
        germination.record(a_test())

        assert germination.for_lot(LOT)[0].treatment is Treatment.NONE

    def test_a_prechilled_test_comes_back_prechilled(self, germination) -> None:
        germination.record(
            a_test(normal=92, fresh=4, treatment=Treatment.PRECHILL, is_retest=True)
        )

        assert germination.for_lot(LOT)[0].treatment is Treatment.PRECHILL

    def test_every_treatment_survives_a_round_trip(self, germination) -> None:
        for treatment in Treatment:
            germination.record(a_test(treatment=treatment, is_retest=True))

        stored = [test.treatment for test in germination.for_lot(LOT)]

        assert stored == list(Treatment)

    def test_the_retest_flag_and_the_treatment_are_separate(self, germination) -> None:
        # A retest with nothing done to it is a real thing: the first test was
        # spoiled, not dormant.
        germination.record(a_test(is_retest=True))

        stored = germination.for_lot(LOT)[0]

        assert stored.is_retest is True
        assert stored.treatment is Treatment.NONE

    def test_the_tests_come_back_in_the_order_they_were_done(self, germination) -> None:
        germination.record(a_test(normal=80, fresh=16))
        germination.record(
            a_test(normal=92, fresh=4, treatment=Treatment.PRECHILL, is_retest=True)
        )

        stored = germination.for_lot(LOT)

        assert [test.treatment for test in stored] == [
            Treatment.NONE,
            Treatment.PRECHILL,
        ]


class TestTheColumnArrivingOnAnExistingDatabase:
    def test_a_test_recorded_before_the_migration_reads_as_untreated(self, tmp_path) -> None:
        path = tmp_path / "arc.sqlite3"
        connection = connect(path, journal_mode="memory")

        # Migrate as far as the release before the treatment column, put a
        # test in, then let the rest of the migrations run over it.
        before = tuple(m for m in MIGRATIONS if m.version <= 5)
        migrate(connection, before)
        LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
        connection.execute(
            """
            insert into germination_test
                (lot_reference, seeds_per_replicate, replicate_count, set_down_on,
                 final_count_on, analyst, is_retest, mean_normal, replicate_range)
            values (?, 100, 4, '2024-11-05', '2024-11-13', 'J. Whitfield', 0, 96, '2.0')
            """,
            (LOT,),
        )
        for position in range(1, 5):
            connection.execute(
                """
                insert into germination_replicate
                    (test_id, position, normal, abnormal, hard, fresh, dead)
                values (1, ?, 96, 4, 0, 0, 0)
                """,
                (position,),
            )

        migrate(connection)

        stored = GerminationRepository(connection).for_lot(LOT)
        assert stored[0].treatment is Treatment.NONE
        assert applied_versions(connection)[-1] == MIGRATIONS[-1].version

        connection.close()


class TestWhatTheRulesMakeOfWhatWasStored:
    def test_a_dormant_test_read_back_is_still_refused(self, germination) -> None:
        germination.record(a_test(normal=80, fresh=16))

        stored = germination.for_lot(LOT)[0]
        broken = check_treatment(stored, register.require("wheat"))

        assert [rule.code for rule in broken] == ["DORMANCY_NOT_BROKEN"]

    def test_and_the_treated_retest_read_back_is_accepted(self, germination) -> None:
        germination.record(
            a_test(normal=92, fresh=4, treatment=Treatment.PRECHILL, is_retest=True)
        )

        stored = germination.for_lot(LOT)[0]

        assert check_treatment(stored, register.require("wheat")) == []
