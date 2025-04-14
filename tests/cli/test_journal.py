"""The day book, filled in by the commands that change something.

The distinction being tested is between a command that does something and one
that only looks. Looking at a lot leaves no trace, because a day book that
records every time somebody read a screen is a day book nobody can find
anything in.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def worked(run):
    run(
        "--operator",
        "jwhitfield",
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


def record_purity(run, operator: str = "jwhitfield"):
    return run(
        "--operator",
        operator,
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


def record_germination(run, operator: str = "rnaylor"):
    return run(
        "--operator",
        operator,
        "germination",
        "record",
        "L-2024-0041",
        "--tray",
        "96,4,0,0,0",
        "--tray",
        "95,5,0,0,0",
        "--tray",
        "97,3,0,0,0",
        "--tray",
        "96,4,0,0,0",
        "--set-down",
        "2024-09-20",
        "--final-count",
        "2024-09-28",
        "--analyst",
        "J. Whitfield",
    )


class TestWhatGetsWrittenDown:
    def test_booking_a_lot_in(self, worked) -> None:
        shown = worked("journal")

        assert "booked in L-2024-0041" in shown.output

    def test_the_operator_is_named(self, worked) -> None:
        assert "jwhitfield" in worked("journal").output

    def test_the_detail_says_what_it_was(self, worked) -> None:
        shown = worked("journal")

        assert "24000 kg of Triticum aestivum" in shown.output

    def test_recording_a_purity(self, worked) -> None:
        record_purity(worked)

        assert "recorded a purity for L-2024-0041" in worked("journal").output

    def test_recording_a_germination_says_what_it_came_to(self, worked) -> None:
        record_germination(worked)

        assert "96 per cent" in worked("journal").output

    def test_issuing_a_certificate(self, worked) -> None:
        record_purity(worked)
        record_germination(worked)
        worked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        assert "issued GB-0214/2024/00001" in worked("journal").output

    def test_the_entries_are_in_the_order_they_happened(self, worked) -> None:
        record_purity(worked)
        record_germination(worked)

        lines = worked("journal", "--subject", "L-2024-0041").output.splitlines()

        assert "booked in" in lines[0]
        assert "purity" in lines[1]
        assert "germination" in lines[2]


class TestWhatDoesNot:
    def test_looking_at_a_lot_leaves_no_trace(self, worked) -> None:
        before = worked("journal").output

        worked("lot", "show", "L-2024-0041")

        assert worked("journal").output == before

    def test_nor_does_listing_them(self, worked) -> None:
        before = worked("journal").output

        worked("lot", "list")
        worked("report", "work")

        assert worked("journal").output == before

    def test_a_refused_command_writes_nothing(self, worked) -> None:
        # The lot is already booked in, so this one is refused, and a day book
        # entry saying it happened would be a lie.
        worked(
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

        assert worked("journal").output.count("booked in") == 1

    def test_an_empty_day_book_says_so(self, run) -> None:
        assert "nothing in the day book" in run("journal").output


class TestReadingItBack:
    def test_by_subject(self, worked) -> None:
        record_purity(worked)

        shown = worked("journal", "--subject", "L-2024-0041")

        assert "booked in" in shown.output
        assert "purity" in shown.output

    def test_a_subject_nobody_touched(self, worked) -> None:
        shown = worked("journal", "--subject", "L-2024-9999")

        assert "nothing in the day book" in shown.output

    def test_by_operator(self, worked) -> None:
        record_purity(worked, operator="jwhitfield")
        record_germination(worked, operator="rnaylor")

        shown = worked("journal", "--operator", "rnaylor")

        assert "germination" in shown.output
        assert "purity" not in shown.output

    def test_the_latest_few(self, worked) -> None:
        record_purity(worked)
        record_germination(worked)

        shown = worked("journal", "--limit", "1")

        assert len(shown.output.strip().splitlines()) == 1

    def test_the_date_comes_from_the_day_the_work_was_done(self, worked) -> None:
        # The console tests run with --today fixed, so the entries carry that
        # date rather than whatever day the suite is run on.
        assert "2024-10-02" in worked("journal").output


class TestWhoIsAtTheKeyboard:
    def test_the_operator_can_be_given(self, worked) -> None:
        assert "jwhitfield" in worked("journal").output

    def test_it_falls_back_to_the_account_name(self, run) -> None:
        run(
            "lot",
            "book-in",
            "L-2024-0042",
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

        shown = run("journal")

        assert "booked in L-2024-0042" in shown.output
        assert "unknown" not in shown.output

    def test_the_station_command_says_who_it_thinks_you_are(self, run) -> None:
        result = run("--operator", "apearce", "station")

        assert "operator apearce" in result.output
