"""How far four trays of the same sample may disagree."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.germination.tolerance import (
    REPLICATE_RANGES,
    check_range,
    fold,
    maximum_range_for,
)


class TestFoldingTheTable:
    def test_a_poor_sample_is_looked_up_as_itself(self) -> None:
        assert fold(4) == 4
        assert fold(23) == 23

    def test_a_good_one_is_looked_up_from_the_other_end(self) -> None:
        assert fold(96) == 4
        assert fold(77) == 23

    def test_fifty_folds_onto_itself(self) -> None:
        assert fold(50) == 50

    def test_something_that_is_not_a_germination_is_refused(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            fold(101)
        with pytest.raises(ValueError, match="0 to 100"):
            fold(-1)


class TestTheAllowance:
    def test_a_sample_at_ninety_nine_has_almost_nowhere_to_vary(self) -> None:
        assert maximum_range_for(99) == 5
        assert maximum_range_for(1) == 5

    def test_a_sample_near_half_has_the_most_room(self) -> None:
        assert maximum_range_for(50) == 20
        assert maximum_range_for(55) == 20
        assert maximum_range_for(45) == 20

    def test_the_allowance_widens_as_the_sample_moves_towards_the_middle(self) -> None:
        allowances = [maximum_range_for(mean) for mean in (99, 96, 92, 85, 75, 60, 50)]

        assert allowances == sorted(allowances)

    def test_a_good_sample_and_its_mirror_get_the_same_allowance(self) -> None:
        for mean in range(0, 51):
            assert maximum_range_for(mean) == maximum_range_for(100 - mean)

    def test_the_bands_step_where_the_table_says(self) -> None:
        assert maximum_range_for(98) == 6
        assert maximum_range_for(97) == 7
        assert maximum_range_for(96) == 8
        assert maximum_range_for(95) == 9
        assert maximum_range_for(94) == 10
        assert maximum_range_for(93) == 10
        assert maximum_range_for(92) == 11

    def test_the_table_is_written_in_order_and_reaches_zero(self) -> None:
        floors = [band.at_least for band in REPLICATE_RANGES]

        assert floors == sorted(floors, reverse=True)
        assert floors[-1] == 0

    def test_every_percentage_has_an_answer(self) -> None:
        for mean in range(0, 101):
            assert 5 <= maximum_range_for(mean) <= 20


class TestCheckingATest:
    def test_trays_that_agree_are_within_tolerance(self) -> None:
        check = check_range(96, Decimal(4))

        assert check.within_tolerance
        assert not check.must_be_repeated

    def test_exactly_on_the_allowance_is_still_within_it(self) -> None:
        check = check_range(96, Decimal(8))

        assert check.maximum_range == 8
        assert check.within_tolerance

    def test_a_point_over_it_is_not(self) -> None:
        check = check_range(96, Decimal(9))

        assert not check.within_tolerance
        assert check.must_be_repeated

    def test_the_same_spread_can_pass_at_one_germination_and_fail_at_another(self) -> None:
        # Nine points of spread is fine on a sample germinating at 95 and not
        # on one germinating at 96.
        assert check_range(95, Decimal(9)).within_tolerance
        assert not check_range(96, Decimal(9)).within_tolerance

    def test_the_explanation_names_the_numbers_the_analyst_needs(self) -> None:
        passed = check_range(96, Decimal(4)).explain()
        failed = check_range(96, Decimal(12)).explain()

        assert "within" in passed
        assert "8 allowed" in passed
        assert "outside" in failed
        assert "96 percent" in failed
