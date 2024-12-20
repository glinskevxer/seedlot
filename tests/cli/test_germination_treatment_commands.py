"""Recording a dormant test, and what the console says about it.

Four trays of a hundred, so the counts in the options read straight across to
percentages. A tray written 80,4,0,16,0 is eighty normal, four abnormal and
sixteen fresh, which puts the test well past the five percent line.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def booked(run):
    run(
        "lot",
        "book-in",
        "L-2024-0041",
        "--species",
        "wheat",
        "--weight",
        "24000",
        "--containers",
        "bag",
        "--container-count",
        "480",
        "--merchant",
        "Ravenscar Grain",
        "--sealed-on",
        "2024-09-12",
        "--origin",
        "GB",
    )
    return run


def record(run, tray: str, *extra: str):
    return run(
        "germination",
        "record",
        "L-2024-0041",
        "--tray",
        tray,
        "--tray",
        tray,
        "--tray",
        tray,
        "--tray",
        tray,
        "--set-down",
        "2024-09-20",
        "--final-count",
        "2024-09-28",
        "--analyst",
        "J. Whitfield",
        *extra,
    )


CLEAN = "96,4,0,0,0"
DORMANT = "80,4,0,16,0"
HARD = "84,4,12,0,0"


class TestListingTheTreatments:
    def test_a_cereal_gets_its_list(self, run) -> None:
        result = run("germination", "treatments", "wheat")

        assert result.exit_code == 0
        assert "prechill" in result.output
        assert "potassium nitrate" in result.output

    def test_none_is_on_every_list(self, run) -> None:
        result = run("germination", "treatments", "wheat")

        assert "none" in result.output

    def test_a_legume_treatment_is_not_on_the_cereal_list(self, run) -> None:
        result = run("germination", "treatments", "wheat")

        assert "scarify" not in result.output

    def test_a_grass_can_have_gibberellic_acid(self, run) -> None:
        result = run("germination", "treatments", "perennial ryegrass")

        assert "gibberellic acid" in result.output


class TestRecordingAnOrdinaryTest:
    def test_a_clean_test_goes_in_with_no_treatment(self, booked) -> None:
        result = record(booked, CLEAN)

        assert result.exit_code == 0
        assert "germination 96 percent" in result.output

    def test_and_nothing_is_said_about_dormancy(self, booked) -> None:
        result = record(booked, CLEAN)

        assert "fresh" not in result.output

    def test_hard_seed_is_reported_when_there_is_enough_of_it(self, booked) -> None:
        result = record(booked, HARD)

        assert "hard seed 12 percent" in result.output

    def test_hard_seed_does_not_make_the_test_dormant(self, booked) -> None:
        result = record(booked, HARD)

        assert result.exit_code == 0
        assert "has not finished" not in result.output


class TestRecordingADormantTest:
    def test_a_dormant_test_with_no_treatment_is_refused(self, booked) -> None:
        result = record(booked, DORMANT)

        assert result.exit_code == 2
        assert "test it again" in result.output

    def test_and_nothing_is_stored(self, booked) -> None:
        record(booked, DORMANT)

        shown = booked("germination", "show", "L-2024-0041")

        assert "nothing set down yet" in shown.output

    def test_a_treated_test_has_to_be_marked_as_a_repeat(self, booked) -> None:
        result = record(booked, DORMANT, "--treatment", "prechill")

        assert result.exit_code == 2
        assert "has to be recorded as one" in result.output

    def test_a_treated_repeat_is_accepted(self, booked) -> None:
        result = record(booked, DORMANT, "--treatment", "prechill", "--retest")

        assert result.exit_code == 0
        assert "16 percent fresh" in result.output

    def test_a_dormant_repeat_with_nothing_done_is_accepted(self, booked) -> None:
        # The second test coming back dormant is a fact about the lot, and the
        # analyst has to be able to write it down.
        result = record(booked, DORMANT, "--retest")

        assert result.exit_code == 0

    def test_a_treatment_the_handbook_does_not_give_is_refused(self, booked) -> None:
        result = record(booked, CLEAN, "--treatment", "scarify", "--retest")

        assert result.exit_code == 2
        assert "not a treatment the handbook gives" in result.output

    def test_a_treatment_that_is_not_a_treatment_at_all_is_refused(self, booked) -> None:
        result = record(booked, CLEAN, "--treatment", "shouting at it")

        assert result.exit_code != 0


class TestReadingItBack:
    def test_the_treatment_shows_against_the_test(self, booked) -> None:
        record(booked, DORMANT, "--treatment", "prechill", "--retest")

        shown = booked("germination", "show", "L-2024-0041")

        assert "after prechill" in shown.output

    def test_an_untreated_test_says_nothing_about_treatments(self, booked) -> None:
        record(booked, CLEAN)

        shown = booked("germination", "show", "L-2024-0041")

        assert "after" not in shown.output

    def test_both_tests_show_with_the_repeat_marked(self, booked) -> None:
        record(booked, DORMANT, "--retest")
        record(booked, "92,4,0,4,0", "--treatment", "prechill", "--retest")

        shown = booked("germination", "show", "L-2024-0041")

        assert shown.output.count("(repeat)") == 2
        assert "after prechill" in shown.output
