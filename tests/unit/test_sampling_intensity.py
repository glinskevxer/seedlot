"""How many spearfuls a lot needs, by both tables."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.sampling.intensity import (
    ContainerBand,
    containers_to_open,
    primary_samples_for_containers,
    primary_samples_for_stream,
)


class TestContainerisedLots:
    def test_a_handful_of_containers_is_sampled_three_times_each(self) -> None:
        assert primary_samples_for_containers(2) == 6
        assert primary_samples_for_containers(4) == 12

    def test_but_never_fewer_than_five_spearfuls_in_total(self) -> None:
        # One container times three is three, and three is not enough.
        assert primary_samples_for_containers(1) == 5

    def test_the_band_drops_to_twice_each_at_five_containers(self) -> None:
        assert primary_samples_for_containers(5) == 10
        assert primary_samples_for_containers(8) == 16

    def test_and_to_once_each_at_nine(self) -> None:
        assert primary_samples_for_containers(9) == 9
        assert primary_samples_for_containers(15) == 15

    def test_above_fifteen_it_becomes_a_flat_total(self) -> None:
        assert primary_samples_for_containers(16) == 15
        assert primary_samples_for_containers(30) == 15

    def test_the_flat_total_steps_up_twice_more(self) -> None:
        assert primary_samples_for_containers(31) == 20
        assert primary_samples_for_containers(59) == 20
        assert primary_samples_for_containers(60) == 30
        assert primary_samples_for_containers(4000) == 30

    def test_a_lot_with_no_containers_cannot_be_sampled_this_way(self) -> None:
        with pytest.raises(ValueError, match="at least one container"):
            primary_samples_for_containers(0)

    def test_the_boundaries_are_where_the_table_says(self) -> None:
        # The band changes on the number, not after it.
        assert primary_samples_for_containers(4) == 12
        assert primary_samples_for_containers(5) == 10
        assert primary_samples_for_containers(8) == 16
        assert primary_samples_for_containers(9) == 9


class TestLotsSampledInMotion:
    def test_a_small_lot_gets_the_minimum_and_no_rate_at_all(self) -> None:
        assert primary_samples_for_stream(Decimal("100")) == 5
        assert primary_samples_for_stream(Decimal("500")) == 5

    def test_the_first_rate_is_one_spearful_every_three_hundred_kilograms(self) -> None:
        assert primary_samples_for_stream(Decimal("900")) == 5
        assert primary_samples_for_stream(Decimal("1800")) == 6
        assert primary_samples_for_stream(Decimal("3000")) == 10

    def test_the_rate_never_falls_below_the_bands_minimum(self) -> None:
        # 501 kg over 300 is two spearfuls by rate, and the band says five.
        assert primary_samples_for_stream(Decimal("501")) == 5

    def test_the_middle_band_is_one_every_five_hundred(self) -> None:
        assert primary_samples_for_stream(Decimal("10000")) == 20
        assert primary_samples_for_stream(Decimal("20000")) == 40

    def test_a_part_of_a_rate_still_costs_a_whole_spearful(self) -> None:
        assert primary_samples_for_stream(Decimal("10001")) == 21

    def test_the_top_band_is_one_every_seven_hundred_with_a_high_floor(self) -> None:
        assert primary_samples_for_stream(Decimal("20001")) == 40
        assert primary_samples_for_stream(Decimal("30000")) == 43
        assert primary_samples_for_stream(Decimal("40000")) == 58

    def test_an_empty_lot_cannot_be_sampled(self) -> None:
        with pytest.raises(ValueError, match="no seed in it"):
            primary_samples_for_stream(Decimal("0"))

    def test_the_two_tables_give_different_answers_for_the_same_lot(self) -> None:
        # Twenty four tonnes in 480 bags: thirty spearfuls by container and
        # forty by weight, because the weight lands in a band whose floor is
        # higher than its own rate. The tables are not reconcilable and the
        # station picks by how the lot is put up, not by which is larger.
        assert primary_samples_for_containers(480) == 30
        assert primary_samples_for_stream(Decimal("24000")) == 40


class TestWhichContainersGetOpened:
    def test_every_container_is_opened_when_there_are_few_enough(self) -> None:
        assert containers_to_open(9, primary_samples=9) == 9
        assert containers_to_open(4, primary_samples=12) == 4

    def test_at_least_every_second_container_is_opened_on_a_flat_total(self) -> None:
        # Thirty spearfuls across four hundred bags would be one in thirteen,
        # and the handbook will not have that.
        assert containers_to_open(400, primary_samples=30) == 200

    def test_an_odd_count_rounds_the_every_second_rule_up(self) -> None:
        assert containers_to_open(31, primary_samples=20) == 20
        assert containers_to_open(45, primary_samples=20) == 23

    def test_a_lot_with_no_containers_cannot_be_opened(self) -> None:
        with pytest.raises(ValueError, match="at least one container"):
            containers_to_open(0, primary_samples=5)


class TestTheTableRowsThemselves:
    def test_a_band_cannot_be_both_a_rate_and_a_total(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            ContainerBand(up_to_containers=4, per_container=3, total=15)

    def test_a_band_has_to_be_one_or_the_other(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            ContainerBand(up_to_containers=4)
