"""Searching a big sample for seeds of other species.

The numbers in here are wheat's: a 120 g purity working sample makes a 1200 g
other seed working sample, and a fifth of that is 240 g. Ryegrass is much
smaller and is used wherever the point is that the rule scales with the
species rather than being a constant somebody typed once.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.otherseed.rules import check_search, required_weight_g
from arc.species.model import Species


def a_search(
    *,
    kind: SearchKind = SearchKind.COMPLETE,
    weight: str = "1200",
    findings: tuple[Finding, ...] = (),
    sought: tuple[str, ...] = (),
    analyst: str = "J. Whitfield",
) -> OtherSeedSearch:
    return OtherSeedSearch(
        species_name="Triticum aestivum",
        kind=kind,
        weight_examined_g=Decimal(weight),
        findings=findings,
        sought=sought,
        analyst=analyst,
    )


def codes(search: OtherSeedSearch, species: Species) -> list[str]:
    return [rule.code for rule in check_search(search, species)]


class TestWhatAFindingWillAccept:
    def test_a_count_is_a_whole_number_of_seeds(self) -> None:
        assert Finding("Avena fatua", 4).count == 4

    def test_zero_is_a_real_finding(self) -> None:
        # Writing the zero down says the analyst looked. Leaving the species
        # out says nothing at all.
        assert Finding("Avena fatua", 0).count == 0

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            Finding("Avena fatua", -1)

    def test_a_finding_has_to_name_something(self) -> None:
        with pytest.raises(ValueError, match="name the species"):
            Finding("   ", 3)

    def test_the_key_ignores_case_and_spacing(self) -> None:
        assert Finding("  Avena Fatua ", 1).key == "avena fatua"


class TestWhatASearchKnowsAboutItself:
    def test_a_search_has_to_have_gone_through_something(self) -> None:
        with pytest.raises(ValueError, match="how much seed"):
            a_search(weight="0")

    def test_nothing_found_is_a_nil_return(self) -> None:
        assert a_search().nil_return is True

    def test_a_zero_count_is_still_a_nil_return(self) -> None:
        search = a_search(findings=(Finding("Avena fatua", 0),))

        assert search.nil_return is True
        assert search.total_found == 0

    def test_counts_add_up_across_species(self) -> None:
        search = a_search(findings=(Finding("Avena fatua", 4), Finding("Galium aparine", 2)))

        assert search.total_found == 6
        assert search.nil_return is False

    def test_a_species_that_was_not_found_counts_zero(self) -> None:
        search = a_search(findings=(Finding("Avena fatua", 4),))

        assert search.count_of("Galium aparine") == 0

    def test_looking_a_count_up_ignores_case(self) -> None:
        search = a_search(findings=(Finding("Avena fatua", 4),))

        assert search.count_of("AVENA FATUA") == 4


class TestScalingToAKilogram:
    def test_four_seeds_in_1200_grams(self) -> None:
        search = a_search(findings=(Finding("Avena fatua", 4),))

        assert search.rate_per_kg("Avena fatua") == Decimal("3.3")

    def test_the_same_four_seeds_in_a_reduced_search_read_much_higher(self) -> None:
        # This is the whole reason the weight examined goes on the certificate.
        # The identical count off a fifth of the seed is five times the rate.
        reduced = a_search(
            kind=SearchKind.REDUCED,
            weight="240",
            findings=(Finding("Avena fatua", 4),),
            sought=("Avena fatua",),
        )

        assert reduced.rate_per_kg("Avena fatua") == Decimal("16.7")

    def test_a_species_not_found_scales_to_nothing(self) -> None:
        assert a_search().rate_per_kg("Avena fatua") == Decimal("0.0")


class TestTheWorksheetLine:
    def test_a_nil_return_says_what_was_searched(self) -> None:
        assert a_search().describe() == "none found in 1200.0 g, complete search"

    def test_findings_are_listed_with_the_weight_and_the_kind(self) -> None:
        search = a_search(
            kind=SearchKind.LIMITED,
            findings=(Finding("Avena fatua", 4), Finding("Galium aparine", 2)),
            sought=("Avena fatua", "Galium aparine"),
        )

        assert search.describe() == (
            "Avena fatua 4, Galium aparine 2 in 1200.0 g, limited search"
        )

    def test_a_species_counted_zero_is_left_off_the_line(self) -> None:
        search = a_search(
            kind=SearchKind.LIMITED,
            findings=(Finding("Avena fatua", 4), Finding("Galium aparine", 0)),
            sought=("Avena fatua", "Galium aparine"),
        )

        assert "Galium" not in search.describe()


class TestHowMuchSeedTheSearchNeeds:
    def test_a_complete_search_takes_ten_purity_samples(self, wheat: Species) -> None:
        assert required_weight_g(wheat, SearchKind.COMPLETE) == Decimal("1200.0")

    def test_a_limited_search_takes_the_same_weight(self, wheat: Species) -> None:
        # Limited means fewer species to look for, not less seed to look in.
        assert required_weight_g(wheat, SearchKind.LIMITED) == Decimal("1200.0")

    def test_a_reduced_search_takes_a_fifth(self, wheat: Species) -> None:
        assert required_weight_g(wheat, SearchKind.REDUCED) == Decimal("240.0")

    def test_the_weight_follows_the_species(self, ryegrass: Species) -> None:
        full = required_weight_g(ryegrass, SearchKind.COMPLETE)

        assert full == ryegrass.purity_working_sample_g * 10
        assert full < Decimal("1200.0")


class TestWhatIsRefused:
    def test_a_full_complete_search_is_accepted(self, wheat: Species) -> None:
        assert check_search(a_search(), wheat) == []

    def test_a_short_sample_is_refused_and_says_how_short(self, wheat: Species) -> None:
        broken = check_search(a_search(weight="900"), wheat)

        assert [rule.code for rule in broken] == ["OTHER_SEED_SAMPLE_SHORT"]
        assert "300.0 g short" in broken[0].detail

    def test_a_hair_under_the_nominal_weight_is_fine(self, wheat: Species) -> None:
        # 1194 g is the divider being a divider, not a short search.
        assert codes(a_search(weight="1194"), wheat) == []

    def test_but_a_percent_under_is_not(self, wheat: Species) -> None:
        assert codes(a_search(weight="1188"), wheat) == ["OTHER_SEED_SAMPLE_SHORT"]

    def test_a_reduced_search_is_judged_against_the_reduced_weight(
        self, wheat: Species
    ) -> None:
        search = a_search(kind=SearchKind.REDUCED, weight="240", sought=("Avena fatua",))

        assert codes(search, wheat) == []

    def test_a_targeted_search_has_to_say_what_it_looked_for(self, wheat: Species) -> None:
        search = a_search(kind=SearchKind.LIMITED, sought=())

        assert "OTHER_SEED_NOTHING_SOUGHT" in codes(search, wheat)

    def test_a_complete_search_cannot_carry_a_list(self, wheat: Species) -> None:
        search = a_search(sought=("Avena fatua",))

        assert "OTHER_SEED_COMPLETE_IS_NOT_TARGETED" in codes(search, wheat)

    def test_the_same_species_counted_twice_is_refused(self, wheat: Species) -> None:
        search = a_search(
            findings=(Finding("Avena fatua", 4), Finding("avena fatua", 1)),
        )

        assert "OTHER_SEED_COUNTED_TWICE" in codes(search, wheat)

    def test_finding_the_crop_itself_is_refused(self, wheat: Species) -> None:
        search = a_search(findings=(Finding("Triticum aestivum", 9),))

        assert "OTHER_SEED_IS_THE_CROP" in codes(search, wheat)

    def test_an_unsigned_search_is_refused(self, wheat: Species) -> None:
        assert "OTHER_SEED_UNSIGNED" in codes(a_search(analyst="  "), wheat)


class TestFindingSomethingNobodyLookedFor:
    def test_a_limited_search_cannot_report_an_unsought_species(self, wheat: Species) -> None:
        # The analyst noticing a cleavers seed while counting wild oats does
        # not make the sample a search for cleavers, and a rate calculated
        # from it would be a guess wearing a number's clothes.
        search = a_search(
            kind=SearchKind.LIMITED,
            findings=(Finding("Galium aparine", 2),),
            sought=("Avena fatua",),
        )

        assert "OTHER_SEED_NOT_SOUGHT" in codes(search, wheat)

    def test_a_complete_search_can_report_anything(self, wheat: Species) -> None:
        search = a_search(findings=(Finding("Galium aparine", 2),))

        assert codes(search, wheat) == []

    def test_a_sought_species_is_matched_case_insensitively(self, wheat: Species) -> None:
        search = a_search(
            kind=SearchKind.LIMITED,
            findings=(Finding("Avena fatua", 4),),
            sought=("AVENA FATUA",),
        )

        assert codes(search, wheat) == []

    def test_everything_wrong_comes_back_at_once(self, wheat: Species) -> None:
        search = a_search(
            kind=SearchKind.LIMITED,
            weight="100",
            findings=(Finding("Galium aparine", 2),),
            sought=(),
            analyst="",
        )

        assert set(codes(search, wheat)) == {
            "OTHER_SEED_SAMPLE_SHORT",
            "OTHER_SEED_NOTHING_SOUGHT",
            "OTHER_SEED_NOT_SOUGHT",
            "OTHER_SEED_UNSIGNED",
        }
