"""When the open lots are due, from the console.

The dates here come off the species, so the fixture books in one wheat lot and
one cocksfoot lot and the two are three weeks apart on the same morning.
"""

from __future__ import annotations

import csv
import io

import pytest


def book(run, reference: str, species: str, serial_weight: str = "24000"):
    return run(
        "lot",
        "book-in",
        reference,
        "--species",
        species,
        "--weight",
        serial_weight,
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


@pytest.fixture
def booked(run):
    book(run, "L-2024-0041", "wheat")
    book(run, "L-2024-0042", "cocksfoot", "8000")
    return run


class TestWhenThingsAreDue:
    def test_an_empty_station_has_nothing_open(self, run) -> None:
        assert "nothing is open" in run("report", "due").output

    def test_both_lots_are_listed(self, booked) -> None:
        result = booked("report", "due")

        assert "L-2024-0041" in result.output
        assert "L-2024-0042" in result.output

    def test_the_faster_species_comes_first(self, booked) -> None:
        result = booked("report", "due")
        lines = result.output.strip().splitlines()

        assert "L-2024-0041" in lines[0]
        assert "L-2024-0042" in lines[1]

    def test_the_reason_is_printed_with_the_date(self, booked) -> None:
        result = booked("report", "due")

        assert "not set down yet" in result.output

    def test_setting_a_germination_down_changes_the_date(self, booked) -> None:
        before = booked("report", "due").output

        booked(
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
            "2024-09-28",
            "--final-count",
            "2024-10-06",
            "--analyst",
            "J. Whitfield",
        )

        after = booked("report", "due").output

        assert before != after
        assert "set down 2024-09-28" in after

    def test_a_lot_whose_germination_went_down_too_late_is_already_overdue(
        self, booked
    ) -> None:
        # Set down on the twentieth, eight days to the final count, three for
        # the bench, which is the first of October. Today is the second.
        booked(
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

        result = booked("report", "due", "--late")

        assert "L-2024-0041 was due 2024-10-01" in result.output


class TestTheLateOnes:
    def test_nothing_is_late_on_the_day_things_are_booked(self, booked) -> None:
        assert "nothing is late" in booked("report", "due", "--late").output

    def test_a_lot_sitting_since_last_year_is_late(self, booked) -> None:
        result = booked("--today", "2025-06-01", "report", "due", "--late")

        assert "L-2024-0041" in result.output
        assert "days ago" in result.output

    def test_and_a_reported_lot_drops_off_the_list_entirely(self, booked) -> None:
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
        booked(
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
        booked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        result = booked("--today", "2025-06-01", "report", "due", "--late")

        assert "L-2024-0041" not in result.output


class TestWritingARegisterToAFile:
    def test_the_store_register_keeps_its_line_endings(self, booked, tmp_path) -> None:
        # The csv module writes \r\n and the file has to keep them, or a
        # spreadsheet on Windows reads every row as two.
        target = tmp_path / "store.csv"

        booked("report", "store", "--out", str(target))

        assert b"\r\r\n" not in target.read_bytes()

    def test_the_searches_register_too(self, booked, tmp_path) -> None:
        target = tmp_path / "searches.csv"

        booked("report", "searches", "--out", str(target))

        assert b"\r\r\n" not in target.read_bytes()

    def test_and_it_is_still_readable_as_a_spreadsheet(self, booked, tmp_path) -> None:
        target = tmp_path / "store.csv"
        booked("report", "store", "--out", str(target))

        rows = list(csv.reader(io.StringIO(target.read_text(encoding="utf-8"))))

        assert rows[0][0] == "lot"

    def test_a_directory_that_is_not_there_is_made(self, booked, tmp_path) -> None:
        target = tmp_path / "somewhere" / "else" / "store.csv"

        booked("report", "store", "--out", str(target))

        assert target.exists()


class TestTheWorkListShrinks:
    def test_a_booked_lot_is_on_it(self, booked) -> None:
        assert "L-2024-0041" in booked("report", "work").output

    def test_recording_a_purity_puts_it_in_test(self, booked) -> None:
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

        assert "in test" in booked("lot", "show", "L-2024-0041").output

    def test_and_certifying_it_takes_it_off_the_list(self, booked) -> None:
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
        booked(
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
        booked("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        listed = booked("report", "work")

        assert "L-2024-0041" not in listed.output
        assert "reported" in booked("lot", "show", "L-2024-0041").output
