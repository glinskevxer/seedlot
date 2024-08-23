"""The species register, and the handbook numbers it carries."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.errors import ConfigurationError, NotFound
from arc.species import SPECIES_TABLE, SpeciesRegister, register
from arc.species.model import (
    GerminationMethod,
    Grinding,
    MoistureMethod,
    OvenMethod,
    SeedClass,
    Species,
    Substrate,
)


def a_species(**overrides: object) -> Species:
    defaults: dict[str, object] = {
        "botanical_name": "Testium sativum",
        "common_name": "test seed",
        "seed_class": SeedClass.CEREAL,
        "max_lot_kg": 30000,
        "submitted_sample_g": Decimal("1000"),
        "purity_working_sample_g": Decimal("120"),
        "chaffy": False,
        "germination": GerminationMethod(Substrate.BETWEEN_PAPER, "20", 4, 8),
        "moisture": MoistureMethod(OvenMethod.HIGH_CONSTANT_2H, Grinding.FINE),
    }
    defaults.update(overrides)
    return Species(**defaults)  # type: ignore[arg-type]


class TestLookup:
    def test_the_botanical_name_finds_it(self) -> None:
        assert register.require("Triticum aestivum").common_name == "wheat"

    def test_so_does_the_common_name(self) -> None:
        assert register.require("wheat").botanical_name == "Triticum aestivum"

    def test_and_so_does_an_alias(self) -> None:
        assert register.require("canola").botanical_name == "Brassica napus"
        assert register.require("alfalfa").botanical_name == "Medicago sativa"

    def test_case_and_stray_spaces_do_not_matter(self) -> None:
        assert register.require("  TRITICUM   aestivum ").common_name == "wheat"

    def test_a_species_the_station_cannot_test_is_refused_by_name(self) -> None:
        with pytest.raises(NotFound) as caught:
            register.require("Triticum durum")

        assert "Triticum durum" in str(caught.value)

    def test_finding_is_allowed_to_come_back_with_nothing(self) -> None:
        assert register.find("Triticum durum") is None
        assert register.find("wheat") is not None

    def test_membership_reads_the_way_it_looks(self) -> None:
        assert "wheat" in register
        assert "Triticum durum" not in register
        assert 41 not in register

    def test_a_near_miss_gets_suggestions_rather_than_a_guess(self) -> None:
        assert register.suggest("Triticum") == ("Triticum aestivum",)
        assert "Brassica napus" in register.suggest("brassica")
        assert register.suggest("zzz") == ()
        assert register.suggest("  ") == ()


class TestTheTableItself:
    def test_every_species_is_reachable_by_its_own_botanical_name(self) -> None:
        for species in SPECIES_TABLE:
            assert register.require(species.botanical_name) is species

    def test_no_two_species_answer_to_the_same_name(self) -> None:
        seen: set[str] = set()
        for species in SPECIES_TABLE:
            for name in species.names():
                assert name not in seen, f"{name} is claimed twice"
                seen.add(name)

    def test_a_table_with_a_clash_in_it_refuses_to_load(self) -> None:
        with pytest.raises(ConfigurationError, match="claimed by both"):
            SpeciesRegister(
                (
                    a_species(botanical_name="One", aliases=("shared",)),
                    a_species(botanical_name="Two", aliases=("shared",)),
                )
            )

    def test_the_working_sample_never_exceeds_the_sample_it_comes_from(self) -> None:
        for species in SPECIES_TABLE:
            assert species.purity_working_sample_g <= species.submitted_sample_g

    def test_every_germination_method_ends_after_it_starts(self) -> None:
        for species in SPECIES_TABLE:
            method = species.germination
            assert method.final_count_day >= method.first_count_day

    def test_oily_seed_never_goes_in_the_hot_oven(self) -> None:
        # The oil oxidises and the sample gains weight, which reads as
        # moisture that was never in it.
        oilseeds = (
            "Brassica napus",
            "Linum usitatissimum",
            "Glycine max",
            "Helianthus annuus",
        )
        for name in oilseeds:
            assert register.require(name).moisture.oven.is_low_constant

    def test_the_classes_between_them_hold_every_species(self) -> None:
        counted = sum(len(register.in_class(seed_class)) for seed_class in SeedClass)

        assert counted == len(register) == len(SPECIES_TABLE)

    def test_the_grasses_are_all_chaffy_and_the_cereals_mostly_are_not(self) -> None:
        for grass in register.in_class(SeedClass.GRASS):
            assert grass.chaffy, f"{grass.botanical_name} should be chaffy"

        assert not register.require("wheat").chaffy
        assert register.require("oat").chaffy


class TestOneSpecies:
    def test_it_prints_both_names(self) -> None:
        assert str(register.require("wheat")) == "Triticum aestivum (wheat)"

    def test_counting_other_seeds_takes_ten_times_the_purity_sample(self) -> None:
        wheat = register.require("wheat")

        assert wheat.purity_working_sample_g == Decimal("120")
        assert wheat.other_seed_working_sample_g == Decimal("1200")

    def test_a_prechill_adds_to_how_long_the_test_takes(self) -> None:
        ryegrass = register.require("perennial ryegrass")

        assert ryegrass.germination.needs_prechill
        assert ryegrass.germination.duration_days == 19

    def test_a_test_without_a_prechill_takes_as_long_as_it_runs(self) -> None:
        wheat = register.require("wheat")

        assert not wheat.germination.needs_prechill
        assert wheat.germination.duration_days == 8

    def test_a_species_without_a_sensible_lot_size_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive maximum lot weight"):
            a_species(max_lot_kg=0)

        with pytest.raises(ValueError, match="positive submitted sample"):
            a_species(submitted_sample_g=Decimal("0"))

    def test_a_working_sample_bigger_than_its_parent_is_refused(self) -> None:
        with pytest.raises(ValueError, match="larger than"):
            a_species(
                submitted_sample_g=Decimal("100"),
                purity_working_sample_g=Decimal("101"),
            )

    def test_a_count_before_the_first_day_is_refused(self) -> None:
        with pytest.raises(ValueError, match="before the first day"):
            GerminationMethod(Substrate.TOP_OF_PAPER, "20", 0, 7)

        with pytest.raises(ValueError, match="before the first count"):
            GerminationMethod(Substrate.TOP_OF_PAPER, "20", 7, 4)

        with pytest.raises(ValueError, match="prechill cannot be negative"):
            GerminationMethod(Substrate.TOP_OF_PAPER, "20", 4, 7, prechill_days=-1)


class TestMethods:
    def test_the_oven_knows_its_own_temperature_and_time(self) -> None:
        assert OvenMethod.LOW_CONSTANT.celsius == 103
        assert OvenMethod.LOW_CONSTANT.hours == Decimal(17)
        assert OvenMethod.HIGH_CONSTANT_2H.celsius == 130
        assert OvenMethod.HIGH_CONSTANT_2H.hours == Decimal(2)

    def test_only_the_low_oven_is_the_low_oven(self) -> None:
        assert OvenMethod.LOW_CONSTANT.is_low_constant
        for hot in (
            OvenMethod.HIGH_CONSTANT_1H,
            OvenMethod.HIGH_CONSTANT_2H,
            OvenMethod.HIGH_CONSTANT_4H,
        ):
            assert not hot.is_low_constant

    def test_whole_seed_is_the_only_grinding_that_is_not_grinding(self) -> None:
        assert not Grinding.NONE.is_required
        assert Grinding.COARSE.is_required
        assert Grinding.FINE.is_required

    def test_a_predry_makes_the_determination_two_stage(self) -> None:
        one_stage = MoistureMethod(OvenMethod.HIGH_CONSTANT_2H, Grinding.FINE)
        two_stage = MoistureMethod(
            OvenMethod.HIGH_CONSTANT_2H, Grinding.FINE, predry_required=True
        )

        assert not one_stage.is_two_stage
        assert two_stage.is_two_stage

    def test_the_substrates_keep_the_codes_the_worksheet_uses(self) -> None:
        assert Substrate.TOP_OF_PAPER.code == "TP"
        assert Substrate.BETWEEN_PAPER.code == "BP"
        assert Substrate.PLEATED_PAPER.code == "PP"
        assert Substrate.SAND.code == "S"
