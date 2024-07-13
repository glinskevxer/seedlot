"""Comparing our result with somebody else's."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.germination.outcome import between_tests_tolerance
from arc.germination.tolerance import maximum_range_for
from arc.referee.between_labs import (
    RefereeVerdict,
    compare_germination,
    compare_purity,
    germination_allowance,
    purity_allowance,
    widens_correctly,
)


def d(value: str) -> Decimal:
    return Decimal(value)


class TestTheThreeAllowancesTogether:
    def test_they_stand_in_the_right_order_at_every_germination(self) -> None:
        for mean in range(0, 101):
            assert widens_correctly(mean), f"the order breaks at {mean}"

    def test_two_laboratories_are_allowed_more_than_two_tests_on_one_bench(self) -> None:
        for mean in (99, 95, 90, 80, 60, 50):
            assert germination_allowance(mean) > between_tests_tolerance(mean)

    def test_but_still_less_than_four_trays_of_one_test(self) -> None:
        for mean in (99, 95, 90, 80, 60, 50):
            assert germination_allowance(mean) <= maximum_range_for(mean)


class TestTheGerminationAllowance:
    def test_a_sample_near_perfect_has_almost_nowhere_to_vary(self) -> None:
        assert germination_allowance(100) == 2
        assert germination_allowance(99) == 3
        assert germination_allowance(1) == 3

    def test_a_sample_near_half_has_the_most_room(self) -> None:
        assert germination_allowance(50) == 11

    def test_a_good_sample_and_its_mirror_get_the_same_allowance(self) -> None:
        for mean in range(0, 51):
            assert germination_allowance(mean) == germination_allowance(100 - mean)

    def test_it_widens_towards_the_middle(self) -> None:
        allowances = [germination_allowance(mean) for mean in (99, 96, 92, 85, 70, 50)]

        assert allowances == sorted(allowances)

    def test_something_that_is_not_a_germination_is_refused(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            germination_allowance(101)


class TestThePurityAllowance:
    def test_it_is_wider_than_the_one_within_a_laboratory(self) -> None:
        from arc.purity.tolerance import tolerance_for

        for average in ("99.8", "98.0", "50.0"):
            within = tolerance_for(d(average), chaffy=False)
            between = purity_allowance(d(average), chaffy=False)

            assert between > within

    def test_chaffy_seed_is_allowed_more_here_too(self) -> None:
        assert purity_allowance(d("98.0"), chaffy=True) > purity_allowance(
            d("98.0"), chaffy=False
        )

    def test_it_is_carried_to_two_places(self) -> None:
        assert purity_allowance(d("98.0"), chaffy=False) == d("1.13")


class TestComparingGerminations:
    def test_two_results_close_together_agree(self) -> None:
        result = compare_germination(96, 95)

        assert result.verdict is RefereeVerdict.AGREE
        assert not result.verdict.needs_a_third_opinion
        assert result.difference == 1

    def test_two_far_apart_go_to_a_third_laboratory(self) -> None:
        result = compare_germination(96, 80)

        assert result.verdict is RefereeVerdict.REFER
        assert result.verdict.needs_a_third_opinion

    def test_exactly_on_the_allowance_still_agrees(self) -> None:
        # Mean 94 folds to 6, which is the five band.
        result = compare_germination(96, 91)

        assert result.allowance == 5
        assert result.difference == 5
        assert result.verdict is RefereeVerdict.AGREE

    def test_a_point_further_apart_does_not(self) -> None:
        assert compare_germination(97, 91).verdict is RefereeVerdict.REFER

    def test_the_order_the_two_are_given_in_does_not_change_the_verdict(self) -> None:
        assert (
            compare_germination(96, 80).verdict is compare_germination(80, 96).verdict
        )

    def test_the_explanation_names_both_results_and_what_follows(self) -> None:
        explained = compare_germination(96, 80).explain()

        assert "we reported 96" in explained
        assert "they reported 80" in explained
        assert "third laboratory" in explained


class TestComparingPurity:
    def test_two_analyses_close_together_agree(self) -> None:
        result = compare_purity(d("98.4"), d("98.6"), chaffy=False)

        assert result.verdict is RefereeVerdict.AGREE

    def test_two_far_apart_go_to_a_third_laboratory(self) -> None:
        result = compare_purity(d("98.4"), d("95.0"), chaffy=False)

        assert result.verdict is RefereeVerdict.REFER

    def test_a_pair_can_agree_between_laboratories_and_not_within_one(self) -> None:
        from arc.purity.tolerance import compare as within_lab

        ours, theirs = d("98.4"), d("97.5")

        assert not within_lab(ours, theirs, chaffy=False).compatible
        assert compare_purity(ours, theirs, chaffy=False).verdict is RefereeVerdict.AGREE

    def test_the_same_pair_can_agree_as_chaffy_and_not_otherwise(self) -> None:
        ours, theirs = d("98.4"), d("97.1")

        assert compare_purity(ours, theirs, chaffy=False).verdict is RefereeVerdict.REFER
        assert compare_purity(ours, theirs, chaffy=True).verdict is RefereeVerdict.AGREE
