"""What the station does with a test once it has been counted."""

from __future__ import annotations

from datetime import date

import pytest

from arc.germination.model import GerminationTest, Replicate
from arc.germination.outcome import (
    Verdict,
    between_tests_tolerance,
    decide,
)


def trays_of(*normals: int) -> tuple[Replicate, ...]:
    """Four trays at the given counts, each adding up to a hundred."""
    return tuple(
        Replicate(normal=count, abnormal=100 - count, hard=0, fresh=0, dead=0)
        for count in normals
    )


def a_test(*normals: int, is_retest: bool = False) -> GerminationTest:
    return GerminationTest(
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        replicates=trays_of(*normals),
        seeds_per_replicate=100,
        set_down_on=date(2024, 9, 20),
        final_count_on=date(2024, 9, 28),
        analyst="J. Whitfield",
        is_retest=is_retest,
    )


class TestBetweenTwoTests:
    def test_two_whole_tests_are_held_tighter_than_four_trays(self) -> None:
        from arc.germination.tolerance import maximum_range_for

        for mean in (99, 95, 90, 80, 60, 50):
            assert between_tests_tolerance(mean) < maximum_range_for(mean)

    def test_a_good_sample_and_its_mirror_get_the_same_allowance(self) -> None:
        for mean in range(0, 51):
            assert between_tests_tolerance(mean) == between_tests_tolerance(100 - mean)

    def test_the_allowance_widens_towards_the_middle(self) -> None:
        allowances = [between_tests_tolerance(mean) for mean in (99, 96, 92, 85, 70, 50)]

        assert allowances == sorted(allowances)

    def test_something_that_is_not_a_germination_is_refused(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            between_tests_tolerance(101)


class TestOneTest:
    def test_a_tidy_test_is_reported_as_it_stands(self) -> None:
        outcome = decide(a_test(96, 96, 95, 97))

        assert outcome.verdict is Verdict.REPORT
        assert outcome.reported_percent == 96
        assert not outcome.needs_more_work

    def test_a_test_that_spread_too_far_is_set_down_again(self) -> None:
        outcome = decide(a_test(99, 96, 92, 87))

        assert outcome.verdict is Verdict.REPEAT
        assert outcome.reported_percent is None
        assert outcome.needs_more_work
        assert "outside" in outcome.reason

    def test_the_verdict_carries_what_the_first_test_said(self) -> None:
        outcome = decide(a_test(99, 96, 92, 87))

        assert outcome.first_percent == 94
        assert outcome.second_percent is None


class TestATestAndItsRepeat:
    def test_a_clean_repeat_settles_it(self) -> None:
        outcome = decide(a_test(99, 96, 92, 87), a_test(94, 95, 94, 95, is_retest=True))

        assert outcome.verdict is Verdict.REPORT
        assert outcome.reported_percent == 95
        assert "the repeat stands" in outcome.reason

    def test_two_scattered_tests_that_agree_are_averaged(self) -> None:
        outcome = decide(
            a_test(99, 96, 92, 87),
            a_test(98, 95, 91, 86, is_retest=True),
        )

        assert outcome.verdict is Verdict.REPORT_MEAN_OF_BOTH
        assert outcome.reported_percent == 94
        assert "they agree with each other" in outcome.reason

    def test_two_scattered_tests_that_disagree_send_the_analyst_back(self) -> None:
        outcome = decide(
            a_test(99, 96, 92, 87),
            a_test(80, 76, 72, 60, is_retest=True),
        )

        assert outcome.verdict is Verdict.DRAW_A_FRESH_SAMPLE
        assert outcome.reported_percent is None
        assert outcome.needs_more_work
        assert "do not agree" in outcome.reason

    def test_a_good_first_test_ends_it_even_with_a_repeat_on_the_bench(self) -> None:
        outcome = decide(a_test(96, 96, 95, 97), a_test(80, 80, 80, 80, is_retest=True))

        assert outcome.verdict is Verdict.REPORT
        assert outcome.reported_percent == 96
        assert outcome.second_percent == 80

    def test_the_mean_of_two_tests_rounds_half_upwards(self) -> None:
        outcome = decide(
            a_test(99, 96, 92, 87),
            a_test(98, 95, 91, 86, is_retest=True),
        )

        assert outcome.first_percent == 94
        assert outcome.second_percent == 93
        assert outcome.reported_percent == 94


class TestTheVerdictsThemselves:
    def test_only_the_two_reporting_verdicts_end_the_work(self) -> None:
        assert Verdict.REPORT.is_final
        assert Verdict.REPORT_MEAN_OF_BOTH.is_final
        assert not Verdict.REPEAT.is_final
        assert not Verdict.DRAW_A_FRESH_SAMPLE.is_final

    def test_they_read_as_instructions(self) -> None:
        assert Verdict.REPEAT.value == "repeat the test"
        assert Verdict.DRAW_A_FRESH_SAMPLE.value == "draw a fresh working sample"
