"""Turning three weighed piles into three percentages."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.errors import RuleBroken
from arc.purity.analysis import (
    Component,
    PurityAnalysis,
    analyse,
    check_analysis,
)
from arc.quantities import Percentage


def an_analysis(
    *,
    working: str = "120.0",
    pure: str = "118.2",
    other: str = "0.9",
    inert: str = "0.9",
) -> PurityAnalysis:
    return PurityAnalysis(
        working_sample_g=Decimal(working),
        pure_seed_g=Decimal(pure),
        other_seed_g=Decimal(other),
        inert_matter_g=Decimal(inert),
        analyst="J. Whitfield",
    )


class TestWhatCameBackOffTheBoard:
    def test_the_recovered_weight_is_the_three_piles_together(self) -> None:
        assert an_analysis().recovered_g == Decimal("120.0")

    def test_a_clean_analysis_has_lost_nothing(self) -> None:
        assert an_analysis().loss_g == 0
        assert an_analysis().loss_fraction == 0

    def test_seed_that_went_on_the_floor_shows_as_a_loss(self) -> None:
        analysis = an_analysis(working="120.0", pure="117.0", other="0.9", inert="0.9")

        assert analysis.loss_g == Decimal("1.2")
        assert analysis.loss_fraction == Decimal("0.01")

    def test_piles_that_weigh_more_than_the_sample_show_a_negative_loss(self) -> None:
        analysis = an_analysis(working="120.0", pure="119.0", other="1.0", inert="1.0")

        assert analysis.loss_g == Decimal("-1.0")

    def test_nothing_on_the_board_is_a_programming_mistake(self) -> None:
        with pytest.raises(ValueError, match="nothing was put on the board"):
            an_analysis(working="0")

    def test_a_negative_pile_is_a_programming_mistake(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            an_analysis(inert="-0.1")


class TestWhenTheAnalysisIsVoid:
    def test_a_small_loss_is_expected_and_allowed(self, wheat) -> None:
        assert check_analysis(an_analysis(pure="115.0", other="0.9", inert="0.9"), wheat) == []

    def test_exactly_five_percent_is_still_allowed(self, wheat) -> None:
        # 120 g on the board, 114 g back: six grams, which is five percent.
        assert check_analysis(an_analysis(pure="112.2", other="0.9", inert="0.9"), wheat) == []

    def test_over_five_percent_voids_it(self, wheat) -> None:
        broken = check_analysis(an_analysis(pure="110.0", other="0.9", inert="0.9"), wheat)

        assert [rule.code for rule in broken] == ["PURITY_LOSS_TOO_HIGH"]
        assert "void" in broken[0].detail

    def test_a_gain_over_five_percent_voids_it_just_the_same(self, wheat) -> None:
        broken = check_analysis(an_analysis(pure="128.0", other="0.9", inert="0.9"), wheat)

        assert [rule.code for rule in broken] == ["PURITY_LOSS_TOO_HIGH"]

    def test_a_working_sample_under_the_species_minimum_is_refused(self, wheat) -> None:
        broken = check_analysis(
            an_analysis(working="90.0", pure="88.2", other="0.9", inert="0.9"), wheat
        )

        assert [rule.code for rule in broken] == ["PURITY_SAMPLE_UNDER_WEIGHT"]

    def test_analysing_a_void_analysis_raises_rather_than_returning_a_number(
        self, wheat
    ) -> None:
        with pytest.raises(RuleBroken) as caught:
            analyse(an_analysis(pure="100.0", other="0.9", inert="0.9"), wheat)

        assert caught.value.codes == ["PURITY_LOSS_TOO_HIGH"]


class TestTheResult:
    def test_a_clean_analysis_reports_what_was_weighed(self, wheat) -> None:
        # 118.2 of 120 is 98.50 exactly, and the two small piles are 0.75 each.
        # Both of those round up, so the set overshoots by a tenth and the
        # largest component gives it back. The reported pure seed is 98.4, not
        # the 98.5 the arithmetic on its own would say, and that is the rule
        # working rather than a rounding error.
        result = analyse(an_analysis(), wheat)

        assert result.pure_seed == Percentage("98.4")
        assert result.other_seed == Percentage("0.8")
        assert result.inert_matter == Percentage("0.8")
        assert result.sums_to_hundred

    def test_the_three_percentages_always_add_to_a_hundred(self, wheat) -> None:
        for pure, other, inert in (
            ("118.2", "0.9", "0.9"),
            ("119.94", "0.03", "0.03"),
            ("100.0", "10.0", "10.0"),
            ("119.0", "0.5", "0.5"),
        ):
            result = analyse(an_analysis(pure=pure, other=other, inert=inert), wheat)

            assert result.sums_to_hundred, f"{pure}/{other}/{inert} did not sum"

    def test_the_percentages_come_off_the_recovered_weight(self, wheat) -> None:
        # Three grams lost. Half of what is left is pure seed, so it reports
        # fifty percent, not the forty nine the original weight would give.
        result = analyse(
            an_analysis(working="120.0", pure="58.5", other="58.5", inert="0.0"), wheat
        )

        assert result.pure_seed == Percentage("50.0")
        assert result.other_seed == Percentage("50.0")

    def test_the_precision_comes_from_the_working_sample_weight(self, wheat, rape) -> None:
        heavy = analyse(an_analysis(), wheat)
        light = analyse(
            an_analysis(working="10.0", pure="9.85", other="0.08", inert="0.07"), rape
        )

        assert heavy.weighed_to_places == 1
        assert light.weighed_to_places == 2

    def test_a_component_can_be_asked_for_by_name(self, wheat) -> None:
        result = analyse(an_analysis(), wheat)

        assert result.percentage_of(Component.PURE_SEED) == Percentage("98.4")
        assert result.percentage_of(Component.INERT_MATTER) == Percentage("0.8")

    def test_a_sample_with_nothing_but_pure_seed_reports_a_hundred(self, wheat) -> None:
        result = analyse(an_analysis(pure="120.0", other="0.0", inert="0.0"), wheat)

        assert result.pure_seed == Percentage("100.0")
        assert result.other_seed == Percentage("0.0")

    def test_the_loss_is_carried_through_to_the_result(self, wheat) -> None:
        result = analyse(an_analysis(pure="117.0", other="0.9", inert="0.9"), wheat)

        assert result.loss_fraction == Decimal("0.01")

    def test_the_component_labels_read_the_way_the_certificate_prints_them(self) -> None:
        assert Component.PURE_SEED.label == "pure seed"
        assert Component.OTHER_SEED.label == "other seed"
        assert Component.INERT_MATTER.label == "inert matter"
