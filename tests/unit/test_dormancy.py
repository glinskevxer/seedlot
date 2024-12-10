"""Seed that is neither germinated nor dead.

Every test in here uses four trays of a hundred, so a count in one tray is a
quarter of a percent of the test. That makes the arithmetic checkable by hand,
which matters because the difference between five percent fresh and six percent
fresh is the difference between reporting a lot and testing it again.
"""

from __future__ import annotations

from datetime import date

import pytest

from arc.germination.dormancy import (
    FRESH_SEED_LIMIT,
    HARD_SEED_REPORTED_FROM,
    Dormancy,
    assess,
    check_treatment,
    treatments_for,
)
from arc.germination.model import GerminationTest, Replicate, Treatment
from arc.species.model import Species


def a_test(
    *,
    normal: int = 96,
    abnormal: int = 4,
    hard: int = 0,
    fresh: int = 0,
    dead: int = 0,
    is_retest: bool = False,
    treatment: Treatment = Treatment.NONE,
) -> GerminationTest:
    """Four trays, all counted the same, a hundred seeds each."""
    return GerminationTest(
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        replicates=tuple(
            Replicate(normal=normal, abnormal=abnormal, hard=hard, fresh=fresh, dead=dead)
            for _ in range(4)
        ),
        seeds_per_replicate=100,
        set_down_on=date(2024, 9, 20),
        final_count_on=date(2024, 9, 28),
        analyst="J. Whitfield",
        is_retest=is_retest,
        treatment=treatment,
    )


def codes(test: GerminationTest, species: Species) -> list[str]:
    return [rule.code for rule in check_treatment(test, species)]


class TestReadingDormancyOffATest:
    def test_a_clean_test_has_none(self) -> None:
        found = assess(a_test())

        assert found.fresh_percent == 0
        assert found.hard_percent == 0
        assert found.is_dormant is False

    def test_the_normal_percentage_comes_through(self) -> None:
        assert assess(a_test()).normal_percent == 96

    def test_fresh_seed_is_counted_as_a_percentage_of_the_whole_test(self) -> None:
        # Twelve fresh in each of four trays is forty eight of four hundred.
        found = assess(a_test(normal=84, abnormal=4, fresh=12))

        assert found.fresh_percent == 12

    def test_hard_seed_is_counted_separately(self) -> None:
        found = assess(a_test(normal=84, abnormal=4, hard=12))

        assert found.hard_percent == 12
        assert found.fresh_percent == 0

    def test_a_test_with_no_seeds_says_nothing(self) -> None:
        empty = GerminationTest(
            lot_reference="L-2024-0041",
            species_name="Triticum aestivum",
            replicates=(Replicate(0, 0, 0, 0, 0),),
            seeds_per_replicate=0,
            set_down_on=date(2024, 9, 20),
            final_count_on=date(2024, 9, 28),
            analyst="J. Whitfield",
        )

        with pytest.raises(ValueError, match="says nothing"):
            assess(empty)


class TestWhereTheLineIs:
    def test_five_percent_fresh_is_ordinary(self) -> None:
        assert assess(a_test(normal=91, abnormal=4, fresh=5)).is_dormant is False

    def test_six_percent_is_not(self) -> None:
        assert assess(a_test(normal=90, abnormal=4, fresh=6)).is_dormant is True

    def test_the_limit_is_where_the_constant_says(self) -> None:
        at_the_limit = Dormancy(
            fresh_percent=FRESH_SEED_LIMIT, hard_percent=0, normal_percent=90
        )
        one_past = Dormancy(
            fresh_percent=FRESH_SEED_LIMIT + 1, hard_percent=0, normal_percent=90
        )

        assert at_the_limit.is_dormant is False
        assert one_past.is_dormant is True

    def test_hard_seed_is_reported_from_one_percent(self) -> None:
        assert Dormancy(0, HARD_SEED_REPORTED_FROM, 90).hard_seed_is_reportable is True
        assert Dormancy(0, 0, 90).hard_seed_is_reportable is False

    def test_hard_seed_does_not_make_a_sample_dormant(self) -> None:
        # A legume with a hard coat is not an unfinished test. It is a lot with
        # hard seed in it, and that figure goes on the certificate.
        assert assess(a_test(normal=84, abnormal=4, hard=12)).is_dormant is False


class TestWhatTheSampleCouldStillReach:
    def test_everything_dormant_coming_good(self) -> None:
        found = assess(a_test(normal=84, abnormal=4, hard=6, fresh=6))

        assert found.normal_percent == 84
        assert found.could_still_reach == 96

    def test_a_clean_test_could_reach_what_it_already_did(self) -> None:
        found = assess(a_test())

        assert found.could_still_reach == found.normal_percent


class TestTheSentenceOnTheWorksheet:
    def test_an_ordinary_test_says_so(self) -> None:
        assert "within the ordinary few" in assess(a_test(normal=94, fresh=2)).explain()

    def test_a_dormant_one_names_both_numbers(self) -> None:
        line = assess(a_test(normal=84, abnormal=4, fresh=12)).explain()

        assert "12 percent fresh" in line
        assert "limit of 5" in line
        assert "has not finished" in line


class TestWhichTreatmentsAreAllowed:
    def test_none_is_always_first(self, wheat: Species) -> None:
        assert treatments_for(wheat)[0] is Treatment.NONE

    def test_a_cereal_gets_a_prechill_or_a_nitrate_soak(self, wheat: Species) -> None:
        allowed = treatments_for(wheat)

        assert Treatment.PRECHILL in allowed
        assert Treatment.KNO3 in allowed

    def test_and_not_scarifying(self, wheat: Species) -> None:
        # Scratching the coat off a wheat grain damages the embryo. It is a
        # legume treatment and it is not on the cereal list.
        assert Treatment.SCARIFY not in treatments_for(wheat)

    def test_a_grass_can_have_gibberellic_acid(self, ryegrass: Species) -> None:
        assert Treatment.GIBBERELLIC_ACID in treatments_for(ryegrass)

    def test_every_treatment_that_was_applied_is_declared(self) -> None:
        applied = [t for t in Treatment if t.was_applied]

        assert Treatment.NONE not in applied
        assert all(t.goes_on_the_certificate for t in applied)


class TestWhatMayBeReported:
    def test_a_clean_test_with_no_treatment_is_fine(self, wheat: Species) -> None:
        assert codes(a_test(), wheat) == []

    def test_a_dormant_test_with_no_treatment_is_refused(self, wheat: Species) -> None:
        dormant = a_test(normal=80, abnormal=4, fresh=16)

        assert "DORMANCY_NOT_BROKEN" in codes(dormant, wheat)

    def test_and_the_refusal_says_what_to_do_about_it(self, wheat: Species) -> None:
        dormant = a_test(normal=80, abnormal=4, fresh=16)
        broken = check_treatment(dormant, wheat)

        assert "test it again" in broken[0].detail

    def test_a_dormant_retest_with_no_treatment_is_allowed_through(
        self, wheat: Species
    ) -> None:
        # The second test still coming back dormant is a fact about the lot
        # and the analyst has to be able to record it.
        dormant = a_test(normal=80, abnormal=4, fresh=16, is_retest=True)

        assert codes(dormant, wheat) == []

    def test_a_treated_test_has_to_be_marked_as_a_retest(self, wheat: Species) -> None:
        dormant = a_test(normal=80, abnormal=4, fresh=16, treatment=Treatment.PRECHILL)

        assert "TREATED_TEST_NOT_MARKED" in codes(dormant, wheat)

    def test_a_treated_retest_is_accepted(self, wheat: Species) -> None:
        treated = a_test(
            normal=92, abnormal=4, fresh=4, is_retest=True, treatment=Treatment.PRECHILL
        )

        assert codes(treated, wheat) == []

    def test_a_treatment_off_the_handbook_is_refused(self, wheat: Species) -> None:
        scarified = a_test(treatment=Treatment.SCARIFY)

        assert "TREATMENT_NOT_ALLOWED" in codes(scarified, wheat)

    def test_both_faults_come_back_at_once(self, wheat: Species) -> None:
        dormant = a_test(normal=80, abnormal=4, fresh=16, treatment=Treatment.SCARIFY)

        assert set(codes(dormant, wheat)) == {
            "TREATMENT_NOT_ALLOWED",
            "TREATED_TEST_NOT_MARKED",
        }
