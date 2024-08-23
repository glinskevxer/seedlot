"""The commands an analyst runs standing at the bench."""

from __future__ import annotations

import pytest


@pytest.fixture
def booked(run):
    """A wheat lot, booked in and ready to be worked on."""
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


def record_purity(run, pure="118.2", other="0.9", inert="0.9", duplicate=False):
    args = [
        "purity",
        "record",
        "L-2024-0041",
        "--working",
        "120.0",
        "--pure",
        pure,
        "--other",
        other,
        "--inert",
        inert,
        "--analyst",
        "J. Whitfield",
    ]
    if duplicate:
        args.append("--duplicate")
    return run(*args)


def record_germination(run, *normals, retest=False):
    args = ["germination", "record", "L-2024-0041"]
    for count in normals:
        args += ["--tray", f"{count},{100 - count},0,0,0"]
    args += [
        "--set-down",
        "2024-09-20",
        "--final-count",
        "2024-09-28",
        "--analyst",
        "J. Whitfield",
    ]
    if retest:
        args.append("--retest")
    return run(*args)


class TestRecordingPurity:
    def test_a_good_analysis_prints_the_three_percentages(self, booked) -> None:
        result = record_purity(booked)

        assert result.exit_code == 0
        assert "pure seed    98.4" in result.output
        assert "other seed   0.8" in result.output
        assert "inert matter 0.8" in result.output

    def test_it_is_there_afterwards(self, booked) -> None:
        record_purity(booked)

        shown = booked("purity", "show", "L-2024-0041")

        assert "J. Whitfield" in shown.output
        assert "pure 98.4" in shown.output

    def test_an_analysis_that_lost_too_much_is_refused(self, booked) -> None:
        result = record_purity(booked, pure="100.0")

        assert result.exit_code == 2
        assert "void" in result.output

    def test_a_void_analysis_is_still_kept(self, booked) -> None:
        record_purity(booked, pure="100.0")

        shown = booked("purity", "show", "L-2024-0041")

        assert "void, not worked out" in shown.output

    def test_a_weight_that_is_not_a_number_is_refused(self, booked) -> None:
        result = record_purity(booked, pure="lots")

        assert result.exit_code != 0
        assert "not a weight" in result.output

    def test_a_lot_with_nothing_done_says_so(self, booked) -> None:
        assert "nothing analysed yet" in booked("purity", "show", "L-2024-0041").output

    def test_duplicates_are_compared_when_both_are_there(self, booked) -> None:
        record_purity(booked)
        record_purity(booked, pure="118.4", duplicate=True)

        shown = booked("purity", "show", "L-2024-0041")

        assert "(duplicate)" in shown.output
        assert "within" in shown.output

    def test_duplicates_that_disagree_say_so(self, booked) -> None:
        record_purity(booked)
        record_purity(booked, pure="117.1", other="1.5", inert="1.4", duplicate=True)

        shown = booked("purity", "show", "L-2024-0041")

        assert "outside" in shown.output


class TestRecordingGermination:
    def test_a_tidy_test_prints_the_germination(self, booked) -> None:
        result = record_germination(booked, 96, 95, 97, 96)

        assert result.exit_code == 0
        assert "germination 96 percent" in result.output
        assert "within" in result.output

    def test_a_scattered_test_is_sent_back(self, booked) -> None:
        result = record_germination(booked, 99, 96, 92, 87)

        assert result.exit_code == 2
        assert "set down again" in result.output

    def test_a_scattered_test_is_still_recorded(self, booked) -> None:
        record_germination(booked, 99, 96, 92, 87)

        shown = booked("germination", "show", "L-2024-0041")

        assert "mean 94" in shown.output

    def test_a_tray_in_the_wrong_shape_is_refused(self, booked) -> None:
        result = booked(
            "germination",
            "record",
            "L-2024-0041",
            "--tray",
            "96,4",
            "--set-down",
            "2024-09-20",
            "--final-count",
            "2024-09-28",
            "--analyst",
            "J. Whitfield",
        )

        assert result.exit_code != 0
        assert "not a tray" in result.output

    def test_a_tray_that_does_not_add_up_is_refused(self, booked) -> None:
        result = booked(
            "germination",
            "record",
            "L-2024-0041",
            "--tray",
            "96,2,0,0,0",
            "--tray",
            "96,4,0,0,0",
            "--tray",
            "96,4,0,0,0",
            "--tray",
            "96,4,0,0,0",
            "--set-down",
            "2024-09-20",
            "--final-count",
            "2024-09-28",
            "--analyst",
            "J. Whitfield",
        )

        assert result.exit_code == 2
        assert "accounts for 98 seeds" in result.output

    def test_the_verdict_shows_what_will_be_reported(self, booked) -> None:
        record_germination(booked, 96, 95, 97, 96)

        shown = booked("germination", "show", "L-2024-0041")

        assert "verdict: report" in shown.output
        assert "reporting 96 percent" in shown.output

    def test_a_repeat_that_settles_it_changes_the_verdict(self, booked) -> None:
        record_germination(booked, 99, 96, 92, 87)
        record_germination(booked, 94, 95, 94, 95, retest=True)

        shown = booked("germination", "show", "L-2024-0041")

        assert "(repeat)" in shown.output
        assert "reporting 95 percent" in shown.output

    def test_a_lot_with_nothing_set_down_says_so(self, booked) -> None:
        assert "nothing set down yet" in booked("germination", "show", "L-2024-0041").output


class TestCertificates:
    def test_a_lot_with_nothing_done_is_not_ready(self, booked) -> None:
        shown = booked("certificate", "check", "L-2024-0041")

        assert "nothing yet" in shown.output

    def test_a_complete_lot_reads_as_ready(self, booked) -> None:
        record_purity(booked)
        record_germination(booked, 96, 95, 97, 96)

        shown = booked("certificate", "check", "L-2024-0041")

        assert "ready to certify" in shown.output
        assert "germination 96 percent" in shown.output

    def test_an_unsettled_germination_shows_as_not_ready(self, booked) -> None:
        record_purity(booked)
        record_germination(booked, 99, 96, 92, 87)

        shown = booked("certificate", "check", "L-2024-0041")

        assert "not ready" in shown.output

    def test_issuing_prints_the_number(self, booked) -> None:
        record_purity(booked)
        record_germination(booked, 96, 95, 97, 96)

        result = booked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        assert result.exit_code == 0
        assert "GB-0214/2024/00001" in result.output

    def test_an_incomplete_lot_is_refused_with_the_reason(self, booked) -> None:
        record_purity(booked)

        result = booked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        assert result.exit_code == 2
        assert "germination" in result.output

    def test_a_green_certificate_takes_the_purity_alone(self, booked) -> None:
        record_purity(booked)

        result = booked(
            "certificate",
            "issue",
            "L-2024-0041",
            "--kind",
            "green",
            "--signed-by",
            "A. Pearce",
        )

        assert result.exit_code == 0

    def test_a_certificate_reads_back_with_its_figures(self, booked) -> None:
        record_purity(booked)
        record_germination(booked, 96, 95, 97, 96)
        booked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        shown = booked("certificate", "show", "GB-0214/2024/00001")

        assert "Triticum aestivum" in shown.output
        assert "pure 98.4" in shown.output
        assert "quotable to 2025-09-28" in shown.output

    def test_a_withdrawn_certificate_says_so(self, booked) -> None:
        record_purity(booked)
        booked(
            "certificate",
            "issue",
            "L-2024-0041",
            "--kind",
            "green",
            "--signed-by",
            "A. Pearce",
        )

        booked("certificate", "withdraw", "GB-0214/2024/00001")
        shown = booked("certificate", "show", "GB-0214/2024/00001")

        assert "withdrawn" in shown.output
