"""The allowance between two counts.

Most of these are the table read back, which is worth doing because the table
is the thing a typo would land in and nothing else would notice. The ones that
matter more are the join between the table and the curve, and the property that
the allowance depends on the total rather than on how the total was split.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.otherseed.tolerance import (
    COUNT_BANDS,
    SPREAD_FACTOR,
    TABLE_LIMIT,
    compare,
    tolerance_for,
)


class TestTheTable:
    def test_two_nil_returns_agree_exactly(self) -> None:
        # Nothing found twice leaves no room for chance to have done anything.
        assert tolerance_for(0) == 0

    def test_one_seed_between_them(self) -> None:
        assert tolerance_for(1) == 2

    @pytest.mark.parametrize(
        ("total", "allowance"),
        [(2, 3), (3, 3), (4, 4), (5, 4), (6, 5), (7, 5), (8, 6), (10, 6)],
    )
    def test_the_small_end_row_by_row(self, total: int, allowance: int) -> None:
        assert tolerance_for(total) == allowance

    @pytest.mark.parametrize(
        ("total", "allowance"),
        [(11, 7), (14, 7), (15, 8), (18, 8), (19, 9), (23, 9), (24, 10), (28, 10)],
    )
    def test_the_middle_row_by_row(self, total: int, allowance: int) -> None:
        assert tolerance_for(total) == allowance

    def test_the_last_row_of_the_table(self) -> None:
        assert tolerance_for(34) == 11
        assert tolerance_for(35) == 12
        assert tolerance_for(TABLE_LIMIT) == 12

    def test_the_bands_are_written_in_order(self) -> None:
        totals = [up_to for up_to, _ in COUNT_BANDS]
        allowances = [allowance for _, allowance in COUNT_BANDS]

        assert totals == sorted(totals)
        assert allowances == sorted(allowances)

    def test_the_table_runs_up_to_the_limit_and_stops(self) -> None:
        assert COUNT_BANDS[-1][0] == TABLE_LIMIT

    def test_a_negative_total_is_refused(self) -> None:
        with pytest.raises(ValueError, match="less than nothing"):
            tolerance_for(-1)


class TestWhereTheTableHandsOver:
    def test_the_curve_agrees_with_the_last_row_it_replaces(self) -> None:
        # If these two ever disagree, a lot counted at 40 and a lot counted at
        # 41 would be judged by rules with a step in them, and the step would
        # be at a number nobody chose for a reason.
        from_curve = Decimal(TABLE_LIMIT).sqrt() * SPREAD_FACTOR

        assert int(from_curve) == tolerance_for(TABLE_LIMIT)

    def test_the_first_total_past_the_table_is_one_wider(self) -> None:
        assert tolerance_for(TABLE_LIMIT + 1) == 13

    def test_the_allowance_never_narrows_as_counts_grow(self) -> None:
        allowances = [tolerance_for(total) for total in range(0, 400)]

        assert allowances == sorted(allowances)

    def test_it_keeps_widening_but_slowly(self) -> None:
        # Four times the seeds is twice the allowance, which is the shape of a
        # square root and not of anything else.
        assert tolerance_for(100) == 20
        assert tolerance_for(400) == 39


class TestComparingTwoCounts:
    def test_two_identical_counts_agree(self) -> None:
        assert compare(4, 4).within_tolerance is True

    def test_four_against_seven_is_ordinary_scatter(self) -> None:
        result = compare(4, 7)

        assert result.total == 11
        assert result.difference == 3
        assert result.allowance == 7
        assert result.within_tolerance is True

    def test_four_against_twenty_is_not(self) -> None:
        result = compare(4, 20)

        assert result.difference == 16
        assert result.allowance == 10
        assert result.within_tolerance is False

    def test_the_order_of_the_two_counts_does_not_matter(self) -> None:
        assert compare(20, 4).explain() != compare(4, 20).explain()
        assert compare(20, 4).within_tolerance == compare(4, 20).within_tolerance
        assert compare(20, 4).difference == compare(4, 20).difference

    def test_the_split_does_not_change_the_allowance(self) -> None:
        # Six seeds altogether is six seeds altogether. Chance did not care
        # which sample they turned up in, and neither does the table.
        assert compare(3, 3).allowance == compare(5, 1).allowance
        assert compare(6, 0).allowance == compare(3, 3).allowance

    def test_a_difference_exactly_on_the_allowance_still_agrees(self) -> None:
        result = compare(6, 1)

        assert result.allowance == 5
        assert result.difference == 5
        assert result.within_tolerance is True

    def test_one_seed_past_the_allowance_does_not(self) -> None:
        # Seven and nothing is the same seven seeds as six and one, and it is
        # the split rather than the total that tips this one over.
        result = compare(7, 0)

        assert result.allowance == 5
        assert result.difference == 7
        assert result.within_tolerance is False

    def test_a_nil_return_against_a_real_count(self) -> None:
        result = compare(0, 5)

        assert result.difference == 5
        assert result.allowance == 4
        assert result.within_tolerance is False

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            compare(-1, 4)


class TestTheWorksheetSentence:
    def test_agreement_reads_as_agreement(self) -> None:
        assert compare(4, 7).explain() == (
            "4 against 7, differing by 3 with 7 allowed, within tolerance"
        )

    def test_disagreement_names_both_numbers(self) -> None:
        assert compare(4, 20).explain() == (
            "4 against 20, differing by 16 with 10 allowed, outside tolerance"
        )
