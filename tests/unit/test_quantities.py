"""Weighing precision and the hundred percent rule."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.quantities import (
    Percentage,
    as_percentages,
    decimals_for,
    normalise_to_hundred,
    weigh,
)


def d(value: str) -> Decimal:
    return Decimal(value)


class TestWeighingPrecision:
    def test_a_sample_under_a_gram_is_weighed_to_four_places(self) -> None:
        assert decimals_for(d("0.5")) == 4
        assert decimals_for(d("0.9999")) == 4

    def test_the_band_changes_exactly_on_the_gram(self) -> None:
        assert decimals_for(d("0.999")) == 4
        assert decimals_for(d("1")) == 3

    def test_the_bands_run_all_the_way_up_to_whole_grams(self) -> None:
        assert decimals_for(d("9.99")) == 3
        assert decimals_for(d("10")) == 2
        assert decimals_for(d("99.9")) == 2
        assert decimals_for(d("100")) == 1
        assert decimals_for(d("999.9")) == 1
        assert decimals_for(d("1000")) == 0
        assert decimals_for(d("25000")) == 0

    def test_a_negative_weight_is_a_programming_mistake(self) -> None:
        with pytest.raises(ValueError, match="never negative"):
            decimals_for(d("-1"))

    def test_weighing_rounds_to_the_band_the_weight_falls_in(self) -> None:
        assert weigh(d("0.123456")) == d("0.1235")
        assert weigh(d("4.56789")) == d("4.568")
        assert weigh(d("45.6789")) == d("45.68")
        assert weigh(d("456.789")) == d("456.8")
        assert weigh(d("4567.89")) == d("4568")

    def test_halves_round_up_rather_than_to_even(self) -> None:
        assert weigh(d("120.25"), places=1) == d("120.3")
        assert weigh(d("120.35"), places=1) == d("120.4")

    def test_a_band_can_be_forced_when_the_set_has_already_decided_one(self) -> None:
        # Every component of one analysis is weighed the same way, even the
        # ones that are individually light enough to deserve more places.
        assert weigh(d("0.004"), places=2) == d("0.00")
        assert weigh(d("0.006"), places=2) == d("0.01")


class TestPercentage:
    def test_a_percentage_is_carried_to_one_decimal(self) -> None:
        assert str(Percentage("98.76")) == "98.8"
        assert str(Percentage(99)) == "99.0"

    def test_it_will_not_hold_something_that_is_not_a_percentage(self) -> None:
        with pytest.raises(ValueError, match="0 to 100"):
            Percentage("100.1")
        with pytest.raises(ValueError, match="0 to 100"):
            Percentage("-0.1")

    def test_two_percentages_are_equal_when_they_report_the_same(self) -> None:
        assert Percentage("98.75") == Percentage("98.8")
        assert Percentage("98.7") != Percentage("98.8")
        assert Percentage("1.0") != "1.0"

    def test_they_sort_the_way_numbers_do(self) -> None:
        assert Percentage("1.0") < Percentage("2.0")
        assert sorted([Percentage("9.0"), Percentage("1.0")]) == [
            Percentage("1.0"),
            Percentage("9.0"),
        ]


class TestComponentsOfAnAnalysis:
    def test_weights_become_percentages_of_the_whole(self) -> None:
        parts = as_percentages([d("98.5"), d("1.0"), d("0.5")], d("100"))

        assert parts == [d("98.5"), d("1.0"), d("0.5")]

    def test_taking_a_percentage_of_nothing_is_a_mistake(self) -> None:
        with pytest.raises(ValueError, match="percentages of nothing"):
            as_percentages([d("1")], d("0"))

    def test_a_set_that_already_sums_is_left_alone(self) -> None:
        assert normalise_to_hundred([d("98.5"), d("1.0"), d("0.5")]) == [
            Percentage("98.5"),
            Percentage("1.0"),
            Percentage("0.5"),
        ]

    def test_rounding_drift_lands_on_the_largest_component(self) -> None:
        # Each of these rounds down, leaving 0.1 unaccounted for.
        parts = normalise_to_hundred([d("98.44"), d("1.04"), d("0.52")])

        assert parts == [Percentage("98.5"), Percentage("1.0"), Percentage("0.5")]
        assert sum(part.value for part in parts) == d("100.0")

    def test_drift_the_other_way_also_lands_on_the_largest(self) -> None:
        parts = normalise_to_hundred([d("98.46"), d("1.06"), d("0.56")])

        assert sum(part.value for part in parts) == d("100.0")
        assert parts[0] == Percentage("98.3")

    def test_a_trace_component_is_never_invented_by_the_adjustment(self) -> None:
        # 0.04 rounds to 0.0 and must stay there. Putting the drift on the
        # smallest component would report a contaminant nobody found.
        parts = normalise_to_hundred([d("99.92"), d("0.04"), d("0.04")])

        assert parts[1] == Percentage("0.0")
        assert parts[2] == Percentage("0.0")
        assert sum(part.value for part in parts) == d("100.0")

    def test_an_empty_analysis_has_nothing_to_normalise(self) -> None:
        assert normalise_to_hundred([]) == []

    def test_a_single_component_becomes_the_whole_hundred(self) -> None:
        assert normalise_to_hundred([d("99.97")]) == [Percentage("100.0")]
