"""Moisture and seed weight from the bench."""

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


@pytest.fixture
def grass_booked(run):
    run(
        "lot",
        "book-in",
        "L-2024-0077",
        "--species",
        "perennial ryegrass",
        "--weight",
        "8000",
        "--containers",
        "bag",
        "--container-count",
        "320",
        "--merchant",
        "Scarborough Seeds",
        "--sealed-on",
        "2024-09-14",
        "--origin",
        "GB",
    )
    return run


def record_moisture(run, dry="20.600", stage=None, predry=None, reference="L-2024-0041"):
    args = [
        "moisture",
        "record",
        reference,
        "--container",
        "12.000",
        "--wet",
        "22.000",
        "--dry",
        dry,
        "--analyst",
        "J. Whitfield",
    ]
    if stage:
        args += ["--stage", stage]
    if predry:
        args += ["--predry-percent", predry]
    return run(*args)


TIDY = ("4.51", "4.48", "4.52", "4.49", "4.50", "4.53", "4.47", "4.50")
SCATTERED = ("4.80", "4.20", "4.72", "4.28", "4.65", "4.35", "4.58", "4.42")


def record_seed_weight(run, weights=TIDY, reference="L-2024-0041"):
    args = ["seedweight", "record", reference]
    for weight in weights:
        args += ["--replicate", weight]
    args += ["--analyst", "J. Whitfield"]
    return run(*args)


class TestMoisture:
    def test_a_dry_sample_is_recorded_and_reported(self, booked) -> None:
        result = record_moisture(booked)

        assert result.exit_code == 0
        assert "moisture 14.0 percent" in result.output

    def test_it_is_there_afterwards(self, booked) -> None:
        record_moisture(booked)

        shown = booked("moisture", "show", "L-2024-0041")

        assert "14.0 percent by J. Whitfield" in shown.output
        assert "reporting 14.0 percent" in shown.output

    def test_a_wet_sample_is_told_to_be_predried(self, booked) -> None:
        result = record_moisture(booked, dry="20.000")

        assert "predry the sample" in result.output

    def test_seed_that_is_never_ground_is_never_told_to_predry(self, grass_booked) -> None:
        result = record_moisture(grass_booked, dry="20.000", reference="L-2024-0077")

        assert "predry" not in result.output

    def test_a_second_stage_needs_the_first_stage_figure(self, booked) -> None:
        result = record_moisture(booked, stage="second")

        assert result.exit_code != 0
        assert "first stage figure" in result.output

    def test_the_two_stages_combine_into_one_moisture(self, booked) -> None:
        record_moisture(booked, dry="21.500", stage="predry")
        result = record_moisture(booked, dry="20.600", stage="second", predry="5.0")

        assert "combined 18.3 percent" in result.output
        assert "reporting 18.3 percent" in booked("moisture", "show", "L-2024-0041").output

    def test_duplicates_that_agree_say_so(self, booked) -> None:
        record_moisture(booked, dry="20.600")
        record_moisture(booked, dry="20.590")

        assert "the duplicates agree" in booked("moisture", "show", "L-2024-0041").output

    def test_duplicates_that_disagree_say_so(self, booked) -> None:
        record_moisture(booked, dry="20.600")
        record_moisture(booked, dry="20.400")

        assert "done again" in booked("moisture", "show", "L-2024-0041").output

    def test_a_lot_with_nothing_determined_says_so(self, booked) -> None:
        assert "nothing determined yet" in booked("moisture", "show", "L-2024-0041").output

    def test_a_weighing_that_makes_no_sense_is_refused(self, booked) -> None:
        with pytest.raises(ValueError, match="heavier than it went in"):
            record_moisture(booked, dry="23.000")


class TestSeedWeight:
    def test_a_tidy_determination_prints_the_figure(self, booked) -> None:
        result = record_seed_weight(booked)

        assert result.exit_code == 0
        assert "45.0 g per thousand" in result.output
        assert "within" in result.output

    def test_it_is_there_afterwards(self, booked) -> None:
        record_seed_weight(booked)

        assert "45.0 g per thousand" in booked("seedweight", "show", "L-2024-0041").output

    def test_a_scattered_determination_is_refused_on_wheat(self, booked) -> None:
        result = record_seed_weight(booked, SCATTERED)

        assert result.exit_code == 2
        assert "counted again" in result.output

    def test_the_same_scatter_stands_on_chaffy_seed(self, grass_booked) -> None:
        result = record_seed_weight(grass_booked, SCATTERED, reference="L-2024-0077")

        assert result.exit_code == 0
        assert "6.0 allowed" in result.output

    def test_a_scattered_determination_is_still_recorded(self, booked) -> None:
        record_seed_weight(booked, SCATTERED)

        assert "outside" in booked("seedweight", "show", "L-2024-0041").output

    def test_seven_replicates_is_not_a_determination(self, booked) -> None:
        with pytest.raises(ValueError, match="8 replicates"):
            record_seed_weight(booked, TIDY[:7])

    def test_a_lot_with_nothing_determined_says_so(self, booked) -> None:
        assert "nothing determined yet" in booked("seedweight", "show", "L-2024-0041").output


class TestOnTheCertificate:
    def test_both_figures_reach_the_certificate(self, booked) -> None:
        booked(
            "purity",
            "record",
            "L-2024-0041",
            "--working",
            "120.0",
            "--pure",
            "118.2",
            "--other",
            "0.9",
            "--inert",
            "0.9",
            "--analyst",
            "J. Whitfield",
        )
        record_moisture(booked)
        record_seed_weight(booked)

        booked(
            "certificate",
            "issue",
            "L-2024-0041",
            "--kind",
            "green",
            "--signed-by",
            "A. Pearce",
        )
        shown = booked("certificate", "show", "GB-0214/2024/00001")

        assert "moisture    14.0 percent" in shown.output
        assert "seed weight 45.0 g per thousand" in shown.output

    def test_a_scattered_seed_weight_stops_the_certificate(self, booked) -> None:
        booked(
            "purity",
            "record",
            "L-2024-0041",
            "--working",
            "120.0",
            "--pure",
            "118.2",
            "--other",
            "0.9",
            "--inert",
            "0.9",
            "--analyst",
            "J. Whitfield",
        )
        record_seed_weight(booked, SCATTERED)

        result = booked(
            "certificate",
            "issue",
            "L-2024-0041",
            "--kind",
            "green",
            "--signed-by",
            "A. Pearce",
        )

        assert result.exit_code == 2
        assert "cannot be reported" in result.output

    def test_the_check_command_shows_both(self, booked) -> None:
        record_moisture(booked)
        record_seed_weight(booked)

        shown = booked("certificate", "check", "L-2024-0041")

        assert "moisture    14.0 percent" in shown.output
        assert "seed weight 45.0 g per thousand" in shown.output
