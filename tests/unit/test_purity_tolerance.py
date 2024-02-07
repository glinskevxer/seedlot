"""Whether two analyses of the same sample are allowed to differ."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.purity.tolerance import (
    PURITY_TOLERANCES,
    compare,
    fold,
    tolerance_for,
)


def d(value: str) -> Decimal:
    return Decimal(value)


class TestFoldingTheTable:
    def test_a_small_component_is_looked_up_as_itself(self) -> None:
        assert fold(d("0.2")) == d("0.2")
        assert fold(d("12.5")) == d("12.5")

    def test_a_large_one_is_looked_up_from_the_other_end(self) -> None:
        assert fold(d("99.8")) == d("0.2")
        assert fold(d("87.5")) == d("12.5")

    def test_fifty_folds_onto_itself(self) -> None:
        assert fold(d("50")) == d("50")

    def test_something_that_is_not_a_percentage_is_refused(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            fold(d("100.1"))
        with pytest.raises(ValueError, match="0 to 100"):
            fold(d("-1"))


class TestTheAllowance:
    def test_a_component_near_nothing_gets_the_tightest_allowance(self) -> None:
        assert tolerance_for(d("0.02"), chaffy=False) == d("0.20")

    def test_a_component_near_everything_gets_the_same_one(self) -> None:
        assert tolerance_for(d("99.98"), chaffy=False) == d("0.20")

    def test_a_component_near_half_gets_the_widest(self) -> None:
        assert tolerance_for(d("50.0"), chaffy=False) == d("2.43")
        assert tolerance_for(d("47.0"), chaffy=False) == d("2.43")

    def test_chaffy_seed_is_allowed_to_differ_by_more(self) -> None:
        for average in ("0.02", "1.10", "12.0", "50.0"):
            free = tolerance_for(d(average), chaffy=False)
            chaffy = tolerance_for(d(average), chaffy=True)

            assert chaffy > free, f"chaffy should be wider at {average}"

    def test_the_allowance_widens_as_the_component_grows(self) -> None:
        allowances = [
            tolerance_for(d(average), chaffy=False)
            for average in ("0.02", "0.3", "1.1", "5.5", "22.0", "50.0")
        ]

        assert allowances == sorted(allowances)
        assert len(set(allowances)) == len(allowances)

    def test_the_band_changes_exactly_where_the_table_says(self) -> None:
        assert tolerance_for(d("0.04"), chaffy=False) == d("0.20")
        assert tolerance_for(d("0.05"), chaffy=False) == d("0.23")
        assert tolerance_for(d("0.09"), chaffy=False) == d("0.23")
        assert tolerance_for(d("0.10"), chaffy=False) == d("0.26")

    def test_every_band_is_wider_for_chaffy_seed_than_free_flowing(self) -> None:
        for band in PURITY_TOLERANCES:
            assert band.chaffy > band.non_chaffy, f"band up to {band.up_to}"

    def test_the_bands_are_written_in_order_and_reach_fifty(self) -> None:
        ceilings = [band.up_to for band in PURITY_TOLERANCES]

        assert ceilings == sorted(ceilings)
        assert ceilings[-1] == d("50.00")


class TestComparingTwoAnalyses:
    def test_two_analyses_that_agree_are_compatible(self, wheat) -> None:
        result = compare(d("98.4"), d("98.5"), chaffy=wheat.chaffy)

        assert result.compatible
        assert result.difference == d("0.1")

    def test_two_that_are_far_apart_are_not(self, wheat) -> None:
        result = compare(d("98.4"), d("99.9"), chaffy=wheat.chaffy)

        assert not result.compatible

    def test_the_allowance_is_looked_up_on_the_average_of_the_two(self) -> None:
        # Averaging 99.85 folds to 0.15, which is the 0.29 band.
        result = compare(d("99.8"), d("99.9"), chaffy=False)

        assert result.average == d("99.85")
        assert result.tolerance == d("0.29")

    def test_exactly_on_the_allowance_is_still_compatible(self) -> None:
        result = compare(d("50.00"), d("52.43"), chaffy=False)

        assert result.difference == d("2.43")
        assert result.tolerance == d("2.43")
        assert result.compatible

    def test_a_hair_over_the_allowance_is_not(self) -> None:
        assert not compare(d("50.00"), d("52.44"), chaffy=False).compatible

    def test_the_same_pair_can_pass_as_chaffy_and_fail_as_free_flowing(self) -> None:
        # Averaging 0.325 puts both in the same band, where free flowing seed
        # is allowed 0.36 and chaffy 0.53. The pair differ by 0.45.
        free = compare(d("0.10"), d("0.55"), chaffy=False)
        chaffy = compare(d("0.10"), d("0.55"), chaffy=True)

        assert not free.compatible
        assert chaffy.compatible

    def test_the_order_the_two_are_given_in_does_not_matter(self) -> None:
        one_way = compare(d("98.4"), d("99.1"), chaffy=False)
        other_way = compare(d("99.1"), d("98.4"), chaffy=False)

        assert one_way.compatible == other_way.compatible
        assert one_way.tolerance == other_way.tolerance

    def test_two_identical_analyses_are_always_compatible(self) -> None:
        for value in ("0.0", "0.5", "50.0", "99.9", "100.0"):
            assert compare(d(value), d(value), chaffy=False).compatible

    def test_the_explanation_says_which_way_it_went_and_why(self) -> None:
        passed = compare(d("98.4"), d("98.5"), chaffy=False).explain()
        failed = compare(d("98.4"), d("99.9"), chaffy=True).explain()

        assert "within" in passed
        assert "free flowing" in passed
        assert "outside" in failed
        assert "chaffy" in failed
