"""The sample chain, and what the station will refuse to work on."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from arc.sampling.samples import (
    Determination,
    ReductionMethod,
    SubmittedSample,
    WorkingSample,
    check_submitted_sample,
    methods_allowed_for,
    working_sample_weight_for,
)


def a_sample(
    *,
    weight_g: str = "1000",
    seal_intact: bool = True,
    method: ReductionMethod = ReductionMethod.MECHANICAL_DIVIDER,
    species_name: str = "Triticum aestivum",
) -> SubmittedSample:
    return SubmittedSample(
        lot_reference="L-2024-0041",
        species_name=species_name,
        weight_g=Decimal(weight_g),
        received_on=date(2024, 9, 18),
        seal_intact=seal_intact,
        reduction_method=method,
        sampler="R. Ainsley",
    )


class TestReductionMethods:
    def test_free_flowing_seed_may_be_reduced_any_way(self, wheat) -> None:
        assert set(methods_allowed_for(wheat)) == set(ReductionMethod)

    def test_chaffy_seed_may_only_go_through_a_divider_or_halving(self, ryegrass) -> None:
        assert methods_allowed_for(ryegrass) == (
            ReductionMethod.MECHANICAL_DIVIDER,
            ReductionMethod.MODIFIED_HALVING,
        )

    def test_the_two_hand_methods_are_the_ones_that_need_seed_to_pour(self) -> None:
        assert ReductionMethod.RANDOM_CUPS.needs_free_flowing_seed
        assert ReductionMethod.SPOON.needs_free_flowing_seed
        assert not ReductionMethod.MECHANICAL_DIVIDER.needs_free_flowing_seed
        assert not ReductionMethod.MODIFIED_HALVING.needs_free_flowing_seed


class TestAcceptingTheBag:
    def test_a_good_sample_raises_nothing(self, wheat) -> None:
        assert check_submitted_sample(a_sample(), wheat) == []

    def test_a_broken_seal_stops_everything(self, wheat) -> None:
        broken = check_submitted_sample(a_sample(seal_intact=False), wheat)

        assert [rule.code for rule in broken] == ["SEAL_BROKEN"]
        assert "drawn from the lot" in broken[0].detail

    def test_a_light_bag_is_refused_and_told_how_light(self, wheat) -> None:
        broken = check_submitted_sample(a_sample(weight_g="850"), wheat)

        assert [rule.code for rule in broken] == ["SAMPLE_UNDER_WEIGHT"]
        assert "150 g short" in broken[0].detail

    def test_exactly_the_minimum_is_enough(self, wheat) -> None:
        assert check_submitted_sample(a_sample(weight_g="1000"), wheat) == []

    def test_the_minimum_is_the_species_own(self, ryegrass) -> None:
        # Sixty grams of ryegrass is plenty; sixty grams of wheat is not.
        assert check_submitted_sample(a_sample(weight_g="60"), ryegrass) == []

    def test_a_method_the_seed_will_not_pour_through_is_refused(self, ryegrass) -> None:
        broken = check_submitted_sample(
            a_sample(weight_g="60", method=ReductionMethod.SPOON), ryegrass
        )

        assert [rule.code for rule in broken] == ["REDUCTION_METHOD_NOT_ALLOWED"]
        assert "chaffy" in broken[0].detail

    def test_the_same_method_is_fine_on_seed_that_does_pour(self, wheat) -> None:
        assert check_submitted_sample(a_sample(method=ReductionMethod.SPOON), wheat) == []

    def test_everything_wrong_comes_back_at_once(self, ryegrass) -> None:
        broken = check_submitted_sample(
            a_sample(
                weight_g="20",
                seal_intact=False,
                method=ReductionMethod.RANDOM_CUPS,
            ),
            ryegrass,
        )

        assert [rule.code for rule in broken] == [
            "SEAL_BROKEN",
            "SAMPLE_UNDER_WEIGHT",
            "REDUCTION_METHOD_NOT_ALLOWED",
        ]

    def test_an_empty_bag_is_not_a_sample_at_all(self) -> None:
        with pytest.raises(ValueError, match="empty bag"):
            a_sample(weight_g="0")


class TestWorkingSampleSizes:
    def test_purity_takes_the_species_working_sample(self, wheat) -> None:
        assert working_sample_weight_for(wheat, Determination.PURITY) == Decimal("120")

    def test_counting_other_species_takes_ten_times_that(self, wheat) -> None:
        assert working_sample_weight_for(wheat, Determination.OTHER_SEEDS) == Decimal("1200")

    def test_ground_moisture_samples_need_more_than_whole_seed_ones(
        self, wheat, ryegrass
    ) -> None:
        assert working_sample_weight_for(wheat, Determination.MOISTURE) == Decimal("50")
        assert working_sample_weight_for(ryegrass, Determination.MOISTURE) == Decimal("15")

    def test_thousand_seed_weight_is_taken_from_the_pure_seed_not_the_bag(self, wheat) -> None:
        assert working_sample_weight_for(wheat, Determination.THOUSAND_SEED_WEIGHT) == 0

    def test_asking_what_a_germination_test_weighs_is_a_mistake(self, wheat) -> None:
        with pytest.raises(ValueError, match="counted out, not weighed out"):
            working_sample_weight_for(wheat, Determination.GERMINATION)

    def test_a_working_sample_records_what_it_was_reduced_by(self) -> None:
        sample = WorkingSample(
            submitted_from="L-2024-0041",
            determination=Determination.PURITY,
            weight_g=Decimal("120.4"),
            reduction_method=ReductionMethod.MECHANICAL_DIVIDER,
        )

        assert sample.determination is Determination.PURITY
        assert sample.reduction_method is ReductionMethod.MECHANICAL_DIVIDER

    def test_an_empty_working_sample_is_not_a_sample(self) -> None:
        with pytest.raises(ValueError, match="empty working sample"):
            WorkingSample(
                submitted_from="L-2024-0041",
                determination=Determination.PURITY,
                weight_g=Decimal("0"),
                reduction_method=ReductionMethod.MECHANICAL_DIVIDER,
            )
