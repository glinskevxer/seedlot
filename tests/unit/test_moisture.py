"""Three weighings, and whether a fourth is needed."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.moisture.determination import (
    DUPLICATE_TOLERANCE,
    PREDRY_THRESHOLD,
    Weighing,
    check_duplicates,
    combine_stages,
    moisture_of,
    needs_predrying,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def weighing(container: str = "12.000", wet: str = "22.000", dry: str = "20.600") -> Weighing:
    return Weighing(
        container_g=d(container),
        with_sample_g=d(wet),
        after_drying_g=d(dry),
    )


class TestTheWeighings:
    def test_the_sample_is_what_the_container_gained(self) -> None:
        assert weighing().wet_sample_g == d("10.000")

    def test_the_water_is_what_the_oven_took_off(self) -> None:
        assert weighing().water_lost_g == d("1.400")

    def test_the_dry_matter_is_what_is_left_in_the_container(self) -> None:
        assert weighing().dry_sample_g == d("8.600")

    def test_a_container_that_gained_nothing_had_no_sample_in_it(self) -> None:
        with pytest.raises(ValueError, match="no more with the sample"):
            weighing(container="12.000", wet="12.000")

    def test_a_sample_that_came_out_heavier_is_a_weighing_mistake(self) -> None:
        with pytest.raises(ValueError, match="heavier than it went in"):
            weighing(wet="22.000", dry="22.001")

    def test_a_sample_lighter_than_its_container_is_a_weighing_mistake(self) -> None:
        with pytest.raises(ValueError, match="less than its own container"):
            weighing(container="12.000", wet="22.000", dry="11.900")


class TestTheResult:
    def test_moisture_is_taken_against_the_wet_weight(self) -> None:
        assert moisture_of(weighing()).percent == d("14.0")

    def test_it_is_reported_to_a_tenth(self) -> None:
        assert moisture_of(weighing(dry="20.567")).percent == d("14.3")

    def test_a_bone_dry_sample_reports_nothing(self) -> None:
        assert moisture_of(weighing(dry="22.000")).percent == d("0.0")

    def test_the_result_carries_the_weights_it_came_from(self) -> None:
        result = moisture_of(weighing())

        assert result.wet_sample_g == d("10.000")
        assert result.water_lost_g == d("1.400")

    def test_a_sample_over_seventeen_percent_counts_as_wet(self) -> None:
        assert not moisture_of(weighing(dry="20.600")).is_wet
        assert moisture_of(weighing(dry="20.200")).is_wet

    def test_exactly_on_the_threshold_is_not_wet(self) -> None:
        result = moisture_of(weighing(wet="22.000", dry="20.300"))

        assert result.percent == PREDRY_THRESHOLD
        assert not result.is_wet


class TestWhetherASecondStageIsNeeded:
    def test_a_wet_cereal_has_to_be_predried(self, wheat) -> None:
        wet = moisture_of(weighing(dry="20.000"))

        assert wet.is_wet
        assert needs_predrying(wet, wheat)

    def test_a_dry_cereal_does_not(self, wheat) -> None:
        assert not needs_predrying(moisture_of(weighing()), wheat)

    def test_seed_that_is_never_ground_is_never_predried_however_wet(self, ryegrass) -> None:
        # Nothing to smear, so nothing to predry for.
        wet = moisture_of(weighing(dry="20.000"))

        assert wet.is_wet
        assert not needs_predrying(wet, ryegrass)


class TestPuttingTheStagesTogether:
    def test_the_shared_water_is_not_counted_twice(self) -> None:
        # Naive addition would give 25.0 and the sample is not that wet.
        assert combine_stages(d("5.0"), d("20.0")) == d("24.0")

    def test_a_first_stage_that_took_nothing_off_leaves_the_second_alone(self) -> None:
        assert combine_stages(d("0.0"), d("14.0")) == d("14.0")

    def test_a_second_stage_that_found_nothing_leaves_the_first_alone(self) -> None:
        assert combine_stages(d("6.0"), d("0.0")) == d("6.0")

    def test_the_combination_is_reported_to_a_tenth(self) -> None:
        assert combine_stages(d("4.5"), d("13.7")) == d("17.6")

    def test_the_order_of_the_stages_does_not_change_the_answer(self) -> None:
        assert combine_stages(d("5.0"), d("20.0")) == combine_stages(d("20.0"), d("5.0"))

    def test_the_combination_can_never_reach_a_hundred_from_two_partial_stages(
        self,
    ) -> None:
        assert combine_stages(d("50.0"), d("50.0")) == d("75.0")

    def test_something_that_is_not_a_moisture_content_is_refused(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            combine_stages(d("101"), d("5"))
        with pytest.raises(ValueError, match="0 to 100"):
            combine_stages(d("5"), d("-1"))


class TestDuplicates:
    def test_two_determinations_that_agree_stand(self) -> None:
        assert check_duplicates(moisture_of(weighing()), moisture_of(weighing())) == []

    def test_exactly_on_the_allowance_still_stands(self) -> None:
        first = moisture_of(weighing(dry="20.600"))
        second = moisture_of(weighing(dry="20.580"))

        assert second.percent - first.percent == DUPLICATE_TOLERANCE
        assert check_duplicates(first, second) == []

    def test_a_wider_gap_sends_both_back(self) -> None:
        first = moisture_of(weighing(dry="20.600"))
        second = moisture_of(weighing(dry="20.500"))

        broken = check_duplicates(first, second)

        assert [rule.code for rule in broken] == ["MOISTURE_DUPLICATES_DISAGREE"]
        assert "done again" in broken[0].detail

    def test_the_order_of_the_two_does_not_matter_to_the_verdict(self) -> None:
        # The sentence names them in the order it was given them, which is what
        # the analyst wants to read. The verdict is the same either way round.
        first = moisture_of(weighing(dry="20.600"))
        second = moisture_of(weighing(dry="20.500"))

        one_way = check_duplicates(first, second)
        other_way = check_duplicates(second, first)

        assert [rule.code for rule in one_way] == [rule.code for rule in other_way]
        assert "14.0 and 15.0" in one_way[0].detail
        assert "15.0 and 14.0" in other_way[0].detail
