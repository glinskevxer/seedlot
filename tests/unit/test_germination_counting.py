"""Counting four hundred seeds into five categories."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from arc.germination.model import (
    Category,
    GerminationTest,
    Replicate,
    check_test,
)


def tray(
    normal: int, abnormal: int = 0, hard: int = 0, fresh: int = 0, dead: int = 0
) -> Replicate:
    return Replicate(normal=normal, abnormal=abnormal, hard=hard, fresh=fresh, dead=dead)


def a_test(
    *,
    trays: tuple[Replicate, ...] | None = None,
    seeds_per_replicate: int = 100,
    is_retest: bool = False,
) -> GerminationTest:
    if trays is None:
        trays = (tray(96, 2, 0, 1, 1),) * 4
    return GerminationTest(
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        replicates=trays,
        seeds_per_replicate=seeds_per_replicate,
        set_down_on=date(2024, 9, 20),
        final_count_on=date(2024, 9, 28),
        analyst="J. Whitfield",
        is_retest=is_retest,
    )


class TestTheCategories:
    def test_only_a_normal_seedling_counts_as_germinated(self) -> None:
        assert Category.NORMAL.counts_as_germinated
        for other in (Category.ABNORMAL, Category.HARD, Category.FRESH, Category.DEAD):
            assert not other.counts_as_germinated

    def test_hard_and_fresh_seed_might_still_come_to_something(self) -> None:
        assert Category.HARD.may_still_grow
        assert Category.FRESH.may_still_grow
        assert not Category.DEAD.may_still_grow
        assert not Category.ABNORMAL.may_still_grow

    def test_the_labels_are_what_the_certificate_prints(self) -> None:
        assert Category.NORMAL.label == "normal seedling"
        assert Category.FRESH.label == "fresh ungerminated"


class TestOneTray:
    def test_a_tray_accounts_for_every_seed_on_it(self) -> None:
        assert tray(96, 2, 0, 1, 1).seeds == 100

    def test_a_category_can_be_asked_for_by_name(self) -> None:
        counted = tray(96, 2, 1, 1, 0)

        assert counted.count_of(Category.NORMAL) == 96
        assert counted.count_of(Category.HARD) == 1
        assert counted.count_of(Category.DEAD) == 0

    def test_a_negative_count_is_a_programming_mistake(self) -> None:
        with pytest.raises(ValueError, match="negative count"):
            tray(-1)

    def test_a_percentage_is_taken_against_what_was_put_down(self) -> None:
        assert tray(96).percentage_normal(100) == Decimal(96)
        assert tray(48).percentage_normal(50) == Decimal(96)

    def test_a_tray_with_no_seeds_on_it_is_a_programming_mistake(self) -> None:
        with pytest.raises(ValueError, match="no seeds in it"):
            tray(0).percentage_normal(0)


class TestTheTestAsAWhole:
    def test_four_hundred_seeds_however_they_are_laid_out(self) -> None:
        assert a_test().seeds_tested == 400
        assert a_test(trays=(tray(48),) * 8, seeds_per_replicate=50).seeds_tested == 400

    def test_the_germination_is_the_mean_across_every_tray(self) -> None:
        assert a_test().mean_normal == 96

    def test_it_is_reported_as_a_whole_number(self) -> None:
        uneven = a_test(trays=(tray(96), tray(95), tray(94), tray(93)))

        assert uneven.mean_normal == 95

    def test_a_half_rounds_up_rather_than_to_even(self) -> None:
        # 378 of 400 is 94.5, and the certificate says 95.
        half = a_test(trays=(tray(95), tray(95), tray(94), tray(94)))

        assert half.mean_normal == 95

    def test_the_totals_add_across_the_trays(self) -> None:
        counted = a_test()

        assert counted.total_of(Category.NORMAL) == 384
        assert counted.total_of(Category.ABNORMAL) == 8
        assert counted.total_of(Category.DEAD) == 4

    def test_the_spread_is_the_best_tray_less_the_worst(self) -> None:
        spread = a_test(trays=(tray(98), tray(96), tray(94), tray(92)))

        assert spread.replicate_range == Decimal(6)

    def test_trays_that_all_agree_have_no_spread(self) -> None:
        assert a_test().replicate_range == 0

    def test_how_long_the_test_took_comes_off_the_dates(self) -> None:
        assert a_test().days_taken == 8

    def test_a_test_counted_before_it_was_set_down_is_a_mistake(self) -> None:
        with pytest.raises(ValueError, match="before the test was set down"):
            GerminationTest(
                lot_reference="L-2024-0041",
                species_name="Triticum aestivum",
                replicates=(tray(96),) * 4,
                seeds_per_replicate=100,
                set_down_on=date(2024, 9, 28),
                final_count_on=date(2024, 9, 20),
                analyst="J. Whitfield",
            )

    def test_a_test_with_no_trays_is_not_a_test(self) -> None:
        with pytest.raises(ValueError, match="needs replicates"):
            a_test(trays=())


class TestWhetherTheCountingHoldsUp:
    def test_a_properly_counted_test_raises_nothing(self) -> None:
        assert check_test(a_test()) == []

    def test_a_tray_that_does_not_add_up_is_named(self) -> None:
        full = tray(96, 2, 0, 1, 1)
        short = tray(95, 2, 0, 1, 1)
        broken = check_test(a_test(trays=(full, short, full, full)))

        assert [rule.code for rule in broken] == ["REPLICATE_DOES_NOT_ADD_UP"]
        assert "replicate 2" in broken[0].detail
        assert "99 seeds" in broken[0].detail

    def test_every_bad_tray_is_named_not_just_the_first(self) -> None:
        short = tray(95, 2, 0, 1, 1)
        full = tray(96, 2, 0, 1, 1)
        broken = check_test(a_test(trays=(short, full, short, short)))

        assert len(broken) == 3

    def test_a_tray_with_too_many_seeds_is_just_as_wrong(self) -> None:
        over = tray(97, 2, 0, 1, 1)
        full = tray(96, 2, 0, 1, 1)
        broken = check_test(a_test(trays=(over, full, full, full)))

        assert [rule.code for rule in broken] == ["REPLICATE_DOES_NOT_ADD_UP"]

    def test_the_three_layouts_the_handbook_allows_are_accepted(self) -> None:
        assert check_test(a_test()) == []
        assert check_test(a_test(trays=(tray(48, 2),) * 8, seeds_per_replicate=50)) == []
        assert check_test(a_test(trays=(tray(24, 1),) * 16, seeds_per_replicate=25)) == []

    def test_anything_else_is_refused_and_told_what_is_allowed(self) -> None:
        broken = check_test(a_test(trays=(tray(96, 2, 0, 1, 1),) * 5))

        assert [rule.code for rule in broken] == ["LAYOUT_NOT_ALLOWED"]
        assert "4 of 100" in broken[0].detail
