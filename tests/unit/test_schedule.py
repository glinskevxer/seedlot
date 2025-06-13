"""When a job will be finished.

Wheat is eight days from setting down, cocksfoot is five days of prechill and
then twenty one, so the same lot booked in on the same morning is a fortnight
apart depending only on what is in the bag. That is the whole point of asking
the species rather than adding a fixed number of days.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import make_lot

from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.species import register
from arc.workflow.schedule import BENCH_DAYS, expected_finish, overdue_on

TODAY = date(2025, 3, 24)


def a_lot(*, serial: int = 41, species: str = "Triticum aestivum", status=None):
    lot = make_lot(serial=serial, species_name=species)
    if status is not None:
        lot.move_to(LotStatus.SAMPLED)
        if status is not LotStatus.SAMPLED:
            lot.move_to(LotStatus.IN_TEST)
        if status in (LotStatus.REPORTED, LotStatus.CLOSED):
            lot.move_to(LotStatus.REPORTED)
        if status is LotStatus.CLOSED:
            lot.move_to(LotStatus.CLOSED)
    return lot


def a_test(set_down: date, species: str = "Triticum aestivum") -> GerminationTest:
    return GerminationTest(
        lot_reference="L-2024-0041",
        species_name=species,
        replicates=tuple(
            Replicate(normal=96, abnormal=4, hard=0, fresh=0, dead=0) for _ in range(4)
        ),
        seeds_per_replicate=100,
        set_down_on=set_down,
        final_count_on=set_down + timedelta(days=8),
        analyst="J. Whitfield",
    )


class TestNothingSetDownYet:
    def test_the_clock_starts_today(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert expected.germination_finishes_on == TODAY + timedelta(days=8)

    def test_and_the_bench_work_comes_after_it(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert expected.finish_on == TODAY + timedelta(days=8 + BENCH_DAYS)

    def test_the_reason_says_it_is_not_set_down(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert "not set down yet" in expected.reason

    def test_a_slow_species_takes_much_longer(self) -> None:
        # Five days of prechill and a final count on day twenty one.
        cocksfoot = register.require("cocksfoot")

        expected = expected_finish(
            a_lot(species="Dactylis glomerata"), cocksfoot, (), booked_in_on=TODAY, on=TODAY
        )

        assert expected.germination_finishes_on == TODAY + timedelta(days=26)

    def test_the_same_morning_is_a_fortnight_apart_by_species(self) -> None:
        wheat = expected_finish(
            a_lot(), register.require("wheat"), (), booked_in_on=TODAY, on=TODAY
        )
        grass = expected_finish(
            a_lot(species="Dactylis glomerata"),
            register.require("cocksfoot"),
            (),
            booked_in_on=TODAY,
            on=TODAY,
        )

        assert (grass.finish_on - wheat.finish_on).days == 18


class TestOnceItIsSetDown:
    def test_the_date_comes_off_the_test(self) -> None:
        wheat = register.require("wheat")
        set_down = date(2025, 3, 20)

        expected = expected_finish(
            a_lot(), wheat, (a_test(set_down),), booked_in_on=TODAY, on=TODAY
        )

        assert expected.germination_finishes_on == set_down + timedelta(days=8)

    def test_which_can_be_sooner_than_starting_today(self) -> None:
        wheat = register.require("wheat")

        already = expected_finish(
            a_lot(), wheat, (a_test(date(2025, 3, 20)),), booked_in_on=TODAY, on=TODAY
        )
        not_yet = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert already.finish_on < not_yet.finish_on

    def test_the_reason_names_the_day_it_was_set_down(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(
            a_lot(), wheat, (a_test(date(2025, 3, 20)),), booked_in_on=TODAY, on=TODAY
        )

        assert "2025-03-20" in expected.reason

    def test_a_repeat_pushes_the_date_out(self) -> None:
        # The second test is the one being waited on, so it decides.
        wheat = register.require("wheat")
        tests = (a_test(date(2025, 3, 10)), a_test(date(2025, 3, 22)))

        expected = expected_finish(a_lot(), wheat, tests, booked_in_on=TODAY, on=TODAY)

        assert expected.germination_finishes_on == date(2025, 3, 30)


class TestALotThatIsFinished:
    def test_a_reported_lot_is_done_today(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(
            a_lot(status=LotStatus.REPORTED), wheat, (), booked_in_on=TODAY, on=TODAY
        )

        assert expected.finish_on == TODAY
        assert expected.reason == "already reported"

    def test_a_closed_one_too(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(
            a_lot(status=LotStatus.CLOSED), wheat, (), booked_in_on=TODAY, on=TODAY
        )

        assert expected.reason == "already reported"

    def test_and_a_germination_on_it_does_not_change_that(self) -> None:
        wheat = register.require("wheat")

        expected = expected_finish(
            a_lot(status=LotStatus.REPORTED),
            wheat,
            (a_test(date(2025, 3, 22)),),
            booked_in_on=TODAY,
            on=TODAY,
        )

        assert expected.finish_on == TODAY


class TestCountingDown:
    def test_days_from_today(self) -> None:
        wheat = register.require("wheat")
        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert expected.days_from(TODAY) == 11

    def test_a_date_still_ahead_is_not_overdue(self) -> None:
        wheat = register.require("wheat")
        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert expected.is_overdue_on(TODAY) is False

    def test_the_day_after_the_date_is(self) -> None:
        wheat = register.require("wheat")
        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert expected.is_overdue_on(expected.finish_on + timedelta(days=1)) is True

    def test_the_line_reads_one_way_before_and_another_after(self) -> None:
        wheat = register.require("wheat")
        expected = expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY)

        assert "due" in expected.describe(TODAY)
        assert "days ago" in expected.describe(expected.finish_on + timedelta(days=4))


class TestPickingOutTheLateOnes:
    def test_nothing_late_gives_nothing_back(self) -> None:
        wheat = register.require("wheat")
        expected = (expected_finish(a_lot(), wheat, (), booked_in_on=TODAY, on=TODAY),)

        assert overdue_on(expected, TODAY) == ()

    def test_the_late_ones_come_back_oldest_first(self) -> None:
        wheat = register.require("wheat")
        first = expected_finish(
            a_lot(serial=41), wheat, (a_test(date(2025, 1, 6)),), booked_in_on=TODAY, on=TODAY
        )
        second = expected_finish(
            a_lot(serial=42),
            wheat,
            (a_test(date(2025, 2, 10)),),
            booked_in_on=TODAY,
            on=TODAY,
        )
        third = expected_finish(a_lot(serial=43), wheat, (), booked_in_on=TODAY, on=TODAY)

        late = overdue_on((third, second, first), TODAY)

        assert [item.lot_reference for item in late] == ["L-2024-0041", "L-2024-0042"]
