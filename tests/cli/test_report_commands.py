"""The registers, printed and written."""

from __future__ import annotations

import csv
import io

import pytest


@pytest.fixture
def worked(run, tmp_path):
    """A station with one lot certified and one still on the bench."""
    run(
        "lot", "book-in", "L-2024-0041",
        "--species", "wheat", "--weight", "24000",
        "--containers", "bag", "--container-count", "480",
        "--merchant", "Ravenscar Grain",
        "--sealed-on", "2024-09-12", "--origin", "GB",
    )
    run(
        "lot", "book-in", "L-2024-0077",
        "--species", "perennial ryegrass", "--weight", "8000",
        "--containers", "bag", "--container-count", "320",
        "--merchant", "Scarborough Seeds",
        "--sealed-on", "2024-09-14", "--origin", "GB",
    )
    run(
        "purity", "record", "L-2024-0041",
        "--working", "120.0", "--pure", "118.2",
        "--other", "0.9", "--inert", "0.9",
        "--analyst", "J. Whitfield",
    )
    run(
        "certificate", "issue", "L-2024-0041",
        "--kind", "green", "--signed-by", "A. Pearce",
    )
    return run


class TestTheMondayList:
    def test_an_empty_station_says_so(self, run) -> None:
        assert "nothing open" in run("report", "work").output

    def test_it_lists_what_is_open(self, worked) -> None:
        output = worked("report", "work").output

        assert "L-2024-0041" in output
        assert "L-2024-0077" in output

    def test_it_says_what_has_been_issued(self, worked) -> None:
        output = worked("report", "work").output

        assert "1 issued" in output
        assert "none issued" in output

    def test_quiet_leaves_the_legend_off(self, worked) -> None:
        loud = worked("report", "work").output
        quiet = worked("--quiet", "report", "work").output

        assert "on the bench now" in loud
        assert "on the bench now" not in quiet


class TestOneMerchant:
    def test_a_merchant_with_nothing_says_so(self, worked) -> None:
        result = worked("report", "merchant", "Nobody Ltd")
        assert "nothing open for Nobody Ltd" in result.output

    def test_it_lists_their_lots_and_certificates(self, worked) -> None:
        output = worked("report", "merchant", "Ravenscar Grain").output

        assert "L-2024-0041" in output
        assert "GB-0214/2024/00001" in output

    def test_a_lot_with_nothing_issued_says_so(self, worked) -> None:
        output = worked("report", "merchant", "Scarborough Seeds").output

        assert "L-2024-0077" in output
        assert "nothing issued yet" in output

    def test_the_name_is_matched_however_it_was_typed(self, worked) -> None:
        assert "L-2024-0041" in worked("report", "merchant", "ravenscar grain").output


class TestTheCertificateRegister:
    def test_it_prints_a_sheet_to_the_terminal(self, worked) -> None:
        output = worked("report", "certificates").output

        rows = list(csv.DictReader(io.StringIO(output)))

        assert len(rows) == 1
        assert rows[0]["number"] == "GB-0214/2024/00001"

    def test_it_defaults_to_the_month_the_work_is_dated_in(self, worked) -> None:
        # The certificate was issued on the second of October and the day the
        # commands are running is the same, so the default range finds it.
        assert "GB-0214/2024/00001" in worked("report", "certificates").output

    def test_a_range_that_misses_it_comes_back_with_only_a_header(self, worked) -> None:
        output = worked(
            "report", "certificates", "--from", "2024-11-01", "--to", "2024-11-30"
        ).output

        assert list(csv.DictReader(io.StringIO(output))) == []
        assert output.startswith('"number"')

    def test_a_range_that_ends_before_it_starts_is_refused(self, worked) -> None:
        result = worked(
            "report", "certificates", "--from", "2024-11-01", "--to", "2024-10-01"
        )

        assert result.exit_code != 0
        assert "ends before it starts" in result.output

    def test_it_writes_a_file_when_asked(self, worked, tmp_path) -> None:
        target = tmp_path / "register.csv"

        result = worked("report", "certificates", "--out", str(target))

        assert target.exists()
        assert "wrote 1 certificates" in result.output
        assert '"GB-0214/2024/00001"' in target.read_text()

    def test_the_file_keeps_the_line_endings_the_format_asks_for(
        self, worked, tmp_path
    ) -> None:
        target = tmp_path / "register.csv"
        worked("report", "certificates", "--out", str(target))

        # Read as bytes, because reading as text translates the endings back.
        assert b"\r\n" in target.read_bytes()


class TestExpiringGerminations:
    def test_a_station_with_nothing_says_so(self, run) -> None:
        assert "nothing expiring" in run("report", "expiring").output

    def test_a_green_certificate_with_no_germination_never_expires(self, worked) -> None:
        assert "nothing expiring" in worked("report", "expiring", "--within", "400").output

    def test_a_germination_is_listed_once_it_comes_into_range(self, run) -> None:
        run(
            "lot", "book-in", "L-2024-0041",
            "--species", "wheat", "--weight", "24000",
            "--containers", "bag", "--container-count", "480",
            "--merchant", "Ravenscar Grain",
            "--sealed-on", "2024-09-12", "--origin", "GB",
        )
        run(
            "purity", "record", "L-2024-0041",
            "--working", "120.0", "--pure", "118.2",
            "--other", "0.9", "--inert", "0.9",
            "--analyst", "J. Whitfield",
        )
        run(
            "germination", "record", "L-2024-0041",
            "--tray", "96,4,0,0,0", "--tray", "95,5,0,0,0",
            "--tray", "97,3,0,0,0", "--tray", "96,4,0,0,0",
            "--set-down", "2024-09-20", "--final-count", "2024-09-28",
            "--analyst", "J. Whitfield",
        )
        run("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")

        # Tested on 28 September 2024, so quotable to 28 September 2025.
        assert "nothing expiring" in run("report", "expiring", "--within", "60").output
        assert "GB-0214/2024/00001" in run("report", "expiring", "--within", "400").output

    def test_looking_zero_days_ahead_is_refused(self, run) -> None:
        result = run("report", "expiring", "--within", "0")

        assert result.exit_code != 0
        assert "at least one day" in result.output
