"""The search commands, driven the way an analyst drives them."""

from __future__ import annotations

import pytest

from arc.errors import NotFound


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


def record(run, *extra: str, weight: str = "1200.0"):
    return run(
        "otherseed",
        "record",
        "L-2024-0041",
        "--weight",
        weight,
        "--analyst",
        "J. Whitfield",
        *extra,
    )


class TestAskingHowMuchSeedIsNeeded:
    def test_it_answers_for_a_complete_search(self, run) -> None:
        result = run("otherseed", "needed", "wheat")

        assert result.exit_code == 0
        assert "1200.0 g" in result.output

    def test_a_reduced_search_needs_a_fifth(self, run) -> None:
        result = run("otherseed", "needed", "wheat", "--kind", "reduced")

        assert "240.0 g" in result.output

    def test_it_answers_in_the_species_the_customer_named(self, run) -> None:
        result = run("otherseed", "needed", "bread wheat")

        assert "Triticum aestivum" in result.output

    def test_a_species_the_station_does_not_test_is_refused(self, run) -> None:
        # The command lets the refusal out. Turning it into an exit code is
        # main's job, and there is a test for that where main is.
        with pytest.raises(NotFound):
            run("otherseed", "needed", "moon dust")


class TestRecordingASearch:
    def test_a_nil_return_is_recorded(self, booked) -> None:
        result = record(booked)

        assert result.exit_code == 0
        assert "none found in 1200.0 g, complete search" in result.output

    def test_a_finding_is_recorded_with_its_rate(self, booked) -> None:
        result = record(booked, "--found", "Avena fatua=4")

        assert "Avena fatua 4 in 1200.0 g" in result.output
        assert "3.3 per kg" in result.output

    def test_two_findings_both_land(self, booked) -> None:
        result = record(booked, "--found", "Avena fatua=4", "--found", "Galium aparine=2")

        assert "Avena fatua 4, Galium aparine 2" in result.output

    def test_a_reduced_search_reports_a_higher_rate_off_the_same_count(self, booked) -> None:
        result = record(
            booked,
            "--kind",
            "reduced",
            "--seek",
            "Avena fatua",
            "--found",
            "Avena fatua=4",
            weight="240.0",
        )

        assert "16.7 per kg" in result.output

    def test_the_search_can_be_read_back(self, booked) -> None:
        record(booked, "--found", "Avena fatua=4")

        shown = booked("otherseed", "show", "L-2024-0041")

        assert "Avena fatua 4" in shown.output
        assert "J. Whitfield" in shown.output

    def test_a_lot_with_no_search_says_so(self, booked) -> None:
        shown = booked("otherseed", "show", "L-2024-0041")

        assert "nothing searched yet" in shown.output

    def test_a_targeted_search_shows_what_it_looked_for(self, booked) -> None:
        record(
            booked,
            "--kind",
            "limited",
            "--seek",
            "Avena fatua",
            "--seek",
            "Galium aparine",
        )

        shown = booked("otherseed", "show", "L-2024-0041")

        assert "looked for Avena fatua, Galium aparine" in shown.output


class TestWhatTheCommandRefuses:
    def test_a_short_sample(self, booked) -> None:
        result = record(booked, weight="900")

        assert result.exit_code == 2
        assert "300.0 g short" in result.output

    def test_a_finding_written_without_a_count(self, booked) -> None:
        result = record(booked, "--found", "Avena fatua")

        assert result.exit_code != 0
        assert "Avena fatua=4" in result.output

    def test_a_count_that_is_not_a_number(self, booked) -> None:
        result = record(booked, "--found", "Avena fatua=some")

        assert result.exit_code != 0

    def test_a_negative_count(self, booked) -> None:
        result = record(booked, "--found", "Avena fatua=-1")

        assert result.exit_code != 0

    def test_a_limited_search_with_nothing_to_look_for(self, booked) -> None:
        result = record(booked, "--kind", "limited")

        assert result.exit_code == 2
        assert "has to name them" in result.output

    def test_finding_the_crop_itself(self, booked) -> None:
        result = record(booked, "--found", "Triticum aestivum=9")

        assert result.exit_code == 2
        assert "belongs in the purity analysis" in result.output

    def test_a_lot_nobody_booked_in(self, run) -> None:
        with pytest.raises(NotFound):
            record(run)

    def test_nothing_is_stored_when_the_search_is_refused(self, booked) -> None:
        record(booked, weight="900")

        shown = booked("otherseed", "show", "L-2024-0041")

        assert "nothing searched yet" in shown.output


class TestComparingTwoSearches:
    def test_two_counts_that_agree(self, booked) -> None:
        record(booked, "--found", "Avena fatua=4")
        record(booked, "--found", "Avena fatua=7")

        result = booked("otherseed", "compare", "L-2024-0041", "Avena fatua")

        assert result.exit_code == 0
        assert "within tolerance" in result.output

    def test_two_that_do_not(self, booked) -> None:
        record(booked, "--found", "Avena fatua=4")
        record(booked, "--found", "Avena fatua=20")

        result = booked("otherseed", "compare", "L-2024-0041", "Avena fatua")

        assert result.exit_code == 1
        assert "outside tolerance" in result.output

    def test_one_search_is_not_enough_to_compare(self, booked) -> None:
        record(booked, "--found", "Avena fatua=4")

        result = booked("otherseed", "compare", "L-2024-0041", "Avena fatua")

        assert result.exit_code == 2
        assert "only 1 search" in result.output

    def test_the_latest_two_are_the_ones_compared(self, booked) -> None:
        record(booked, "--found", "Avena fatua=40")
        record(booked, "--found", "Avena fatua=4")
        record(booked, "--found", "Avena fatua=7")

        result = booked("otherseed", "compare", "L-2024-0041", "Avena fatua")

        assert "4 against 7" in result.output
