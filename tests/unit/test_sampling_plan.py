"""The docket the sampler is handed."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.conftest import make_lot

from arc.errors import RuleBroken
from arc.lots.model import ContainerKind
from arc.sampling import SamplingRoute, plan_for


class TestChoosingTheRoute:
    def test_bags_light_enough_to_spear_are_sampled_where_they_stand(self, wheat) -> None:
        plan = plan_for(make_lot(weight_kg="24000", container_count=480), wheat)

        assert plan.route == SamplingRoute.BY_CONTAINER
        assert not plan.is_in_stream
        assert plan.primary_samples == 30
        assert plan.containers_to_open == 240

    def test_bulk_is_sampled_as_it_moves(self, wheat) -> None:
        plan = plan_for(
            make_lot(weight_kg="24000", container_kind=ContainerKind.BULK, container_count=0),
            wheat,
        )

        assert plan.is_in_stream
        assert plan.primary_samples == 40
        assert plan.containers_to_open is None

    def test_big_bags_are_sampled_as_they_move_too(self, wheat) -> None:
        plan = plan_for(
            make_lot(
                weight_kg="24000",
                container_kind=ContainerKind.BIG_BAG,
                container_count=24,
            ),
            wheat,
        )

        assert plan.is_in_stream
        assert plan.primary_samples == 40

    def test_the_same_weight_in_different_packaging_gets_a_different_plan(self, wheat) -> None:
        in_bags = plan_for(make_lot(weight_kg="24000", container_count=480), wheat)
        in_bulk = plan_for(
            make_lot(weight_kg="24000", container_kind=ContainerKind.BULK, container_count=0),
            wheat,
        )

        assert in_bags.primary_samples == 30
        assert in_bulk.primary_samples == 40


class TestWhatComesBack:
    def test_the_minimum_submitted_sample_is_the_species_own(self, wheat, ryegrass) -> None:
        wheat_plan = plan_for(make_lot(), wheat)
        grass_plan = plan_for(
            make_lot(species_name="Lolium perenne", weight_kg="8000", container_count=320),
            ryegrass,
        )

        assert wheat_plan.minimum_submitted_g == Decimal("1000")
        assert grass_plan.minimum_submitted_g == Decimal("60")

    def test_the_plan_names_the_species_botanically(self, wheat) -> None:
        assert plan_for(make_lot(), wheat).species_name == "Triticum aestivum"


class TestTheDocket:
    def test_it_reads_as_instructions(self, wheat) -> None:
        lines = plan_for(make_lot(weight_kg="24000", container_count=480), wheat).docket_lines()

        assert lines == (
            "Lot L-2024-0041",
            "Species Triticum aestivum",
            "Sample by container",
            "Take 30 primary samples",
            "Open at least 240 containers",
            "Submit at least 1000 g",
        )

    def test_a_stream_docket_says_nothing_about_containers(self, wheat) -> None:
        lines = plan_for(
            make_lot(container_kind=ContainerKind.BULK, container_count=0),
            wheat,
        ).docket_lines()

        assert not any("containers" in line for line in lines)
        assert "Sample in stream" in lines


class TestALotThatCannotBeSampled:
    def test_a_lot_over_the_maximum_gets_no_plan_at_all(self, wheat) -> None:
        with pytest.raises(RuleBroken) as caught:
            plan_for(make_lot(weight_kg="40000"), wheat)

        assert caught.value.codes == ["LOT_OVER_MAXIMUM"]

    def test_the_refusal_carries_every_reason_not_just_the_first(self, ryegrass) -> None:
        lot = make_lot(species_name="Lolium perenne", weight_kg="24000", container_count=48)

        with pytest.raises(RuleBroken) as caught:
            plan_for(lot, ryegrass)

        assert caught.value.codes == ["LOT_OVER_MAXIMUM", "BAGS_TOO_HEAVY"]

    def test_a_lot_inside_the_five_percent_allowance_still_gets_one(self, wheat) -> None:
        plan = plan_for(make_lot(weight_kg="31500", container_count=630), wheat)

        assert plan.primary_samples == 30
