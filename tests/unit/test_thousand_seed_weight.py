"""Eight replicates of a hundred seeds, and the scatter between them."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.weight.thousand_seed import (
    CV_LIMIT_CHAFFY,
    CV_LIMIT_FREE_FLOWING,
    check,
    cv_limit_for,
    measure,
)


def weights(*values: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(value) for value in values)


TIDY = weights("4.51", "4.48", "4.52", "4.49", "4.50", "4.53", "4.47", "4.50")
# Around five percent of scatter: over the limit for wheat and under it for
# ryegrass, which is the pair of cases worth having.
SCATTERED = weights("4.80", "4.20", "4.72", "4.28", "4.65", "4.35", "4.58", "4.42")


class TestTheLimit:
    def test_free_flowing_seed_is_held_to_four_percent(self, wheat) -> None:
        assert cv_limit_for(wheat) == CV_LIMIT_FREE_FLOWING
        assert cv_limit_for(wheat) == Decimal("4.0")

    def test_chaffy_seed_is_allowed_six(self, ryegrass) -> None:
        assert cv_limit_for(ryegrass) == CV_LIMIT_CHAFFY
        assert cv_limit_for(ryegrass) == Decimal("6.0")


class TestTheDetermination:
    def test_the_thousand_seed_weight_is_ten_times_the_mean_of_a_hundred(self, wheat) -> None:
        result = measure(TIDY, wheat)

        assert result.grams_per_thousand == Decimal("45.0")

    def test_it_is_reported_to_a_tenth_of_a_gram(self, wheat) -> None:
        result = measure(weights("4.514", *(["4.500"] * 7)), wheat)

        assert result.grams_per_thousand == Decimal("45.0")

    def test_tidy_replicates_have_almost_no_scatter(self, wheat) -> None:
        result = measure(TIDY, wheat)

        assert result.coefficient_of_variation < Decimal("1.0")
        assert result.within_tolerance

    def test_identical_replicates_have_none_at_all(self, wheat) -> None:
        result = measure(weights(*(["4.50"] * 8)), wheat)

        assert result.coefficient_of_variation == Decimal("0.0")
        assert result.standard_deviation_g == 0

    def test_scattered_replicates_are_outside_the_limit_for_free_flowing_seed(
        self, wheat
    ) -> None:
        result = measure(SCATTERED, wheat)

        assert result.coefficient_of_variation > Decimal("4.0")
        assert not result.within_tolerance

    def test_the_same_scatter_passes_on_chaffy_seed(self, ryegrass) -> None:
        result = measure(SCATTERED, ryegrass)

        assert result.coefficient_of_variation < Decimal("6.0")
        assert result.within_tolerance

    def test_the_mean_and_the_deviation_are_kept_for_the_worksheet(self, wheat) -> None:
        result = measure(TIDY, wheat)

        assert result.mean_g > 0
        assert result.standard_deviation_g > 0
        assert len(result.replicate_weights_g) == 8

    def test_the_explanation_says_which_way_it_went(self, wheat, ryegrass) -> None:
        assert "within" in measure(TIDY, wheat).explain()
        assert "outside" in measure(SCATTERED, wheat).explain()
        assert "6.0 allowed" in measure(SCATTERED, ryegrass).explain()


class TestWhatIsRefused:
    def test_seven_replicates_is_not_a_determination(self, wheat) -> None:
        with pytest.raises(ValueError, match="8 replicates"):
            measure(TIDY[:7], wheat)

    def test_nine_is_not_either(self, wheat) -> None:
        with pytest.raises(ValueError, match="8 replicates"):
            measure(TIDY + (Decimal("4.50"),), wheat)

    def test_a_replicate_weighing_nothing_is_a_weighing_mistake(self, wheat) -> None:
        with pytest.raises(ValueError, match="cannot weigh nothing"):
            measure(weights("4.50", "0.00", *(["4.50"] * 6)), wheat)

    def test_a_tidy_determination_raises_nothing(self, wheat) -> None:
        assert check(measure(TIDY, wheat), wheat) == []

    def test_a_scattered_one_is_sent_back_to_be_counted_again(self, wheat) -> None:
        broken = check(measure(SCATTERED, wheat), wheat)

        assert [rule.code for rule in broken] == ["TSW_SCATTER_TOO_WIDE"]
        assert "counted again" in broken[0].detail

    def test_the_same_determination_stands_for_chaffy_seed(self, ryegrass) -> None:
        assert check(measure(SCATTERED, ryegrass), ryegrass) == []
