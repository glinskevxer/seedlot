"""Booking a merchant's list in from the console.

Two lists of problems come out of this and they go to different people. Rows
the file could not turn into a lot are the merchant's to fix. Lots the station
will not accept are a conversation about splitting them, and the advice for
that is printed alongside.
"""

from __future__ import annotations

import pytest

from arc.importing.merchant_csv import COLUMNS

HEADER = ",".join(COLUMNS)
GOOD = "L-2024-0041,wheat,24000,bag,480,2024-09-12,GB"
SECOND = "L-2024-0042,barley,20000,bag,400,2024-09-13,GB"
TOO_HEAVY = "L-2024-0043,wheat,40000,bag,800,2024-09-14,GB"
UNREADABLE = "L-nonsense,wheat,24000,bag,480,2024-09-12,GB"


@pytest.fixture
def a_list(tmp_path):
    def write(*rows: str, name: str = "lots.csv") -> str:
        path = tmp_path / name
        path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
        return str(path)

    return write


def run_import(run, path: str, *extra: str):
    return run("lot", "import", path, "--merchant", "Ravenscar Grain", *extra)


class TestAListThatIsFine:
    def test_the_lots_are_booked_in(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, SECOND))

        assert result.exit_code == 0
        assert "2 booked in" in result.output

    def test_and_they_are_really_there(self, run, a_list) -> None:
        run_import(run, a_list(GOOD, SECOND))

        listed = run("lot", "list")

        assert "L-2024-0041" in listed.output
        assert "L-2024-0042" in listed.output

    def test_the_merchant_comes_from_the_command(self, run, a_list) -> None:
        run_import(run, a_list(GOOD))

        shown = run("lot", "show", "L-2024-0041")

        assert "Ravenscar Grain" in shown.output

    def test_the_species_is_stored_botanically(self, run, a_list) -> None:
        run_import(run, a_list(GOOD))

        shown = run("lot", "show", "L-2024-0041")

        assert "Triticum aestivum" in shown.output


class TestARowTheFileCannotRead:
    def test_it_is_reported_with_its_row_number(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, UNREADABLE))

        assert "row 3" in result.output

    def test_the_good_rows_still_go_in(self, run, a_list) -> None:
        run_import(run, a_list(GOOD, UNREADABLE))

        assert "L-2024-0041" in run("lot", "list").output

    def test_the_command_exits_non_zero(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, UNREADABLE))

        assert result.exit_code == 1

    def test_a_file_with_nothing_readable_in_it(self, run, a_list) -> None:
        result = run_import(run, a_list(UNREADABLE))

        assert result.exit_code == 2
        assert "0 lots, 1 rows to fix" in result.output

    def test_a_file_missing_a_column(self, run, tmp_path) -> None:
        path = tmp_path / "lots.csv"
        path.write_text("lot,species\nL-2024-0041,wheat\n", encoding="utf-8")

        result = run_import(run, str(path))

        assert result.exit_code == 2
        assert "columns are missing" in result.output

    def test_a_file_that_is_not_there(self, run, tmp_path) -> None:
        result = run_import(run, str(tmp_path / "nothing.csv"))

        assert result.exit_code != 0


class TestALotTheStationWillNotAccept:
    def test_a_lot_over_the_maximum_weight_is_refused(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, TOO_HEAVY))

        assert "L-2024-0043" in result.output
        assert "1 booked in, 1 refused" in result.output

    def test_and_the_advice_about_splitting_it_is_printed(self, run, a_list) -> None:
        result = run_import(run, a_list(TOO_HEAVY))

        assert "sublot" in result.output.lower() or "split" in result.output.lower()

    def test_the_others_are_unaffected(self, run, a_list) -> None:
        run_import(run, a_list(GOOD, TOO_HEAVY, SECOND))

        listed = run("lot", "list")

        assert "L-2024-0041" in listed.output
        assert "L-2024-0042" in listed.output
        assert "L-2024-0043" not in listed.output


class TestSayingWhatWouldHappen:
    def test_a_dry_run_says_what_it_would_do(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, SECOND), "--dry-run")

        assert result.exit_code == 0
        assert "2 would be booked in" in result.output

    def test_and_writes_nothing(self, run, a_list) -> None:
        # The connection is in autocommit, so this only holds because the
        # command opens a transaction round the whole list.
        run_import(run, a_list(GOOD, SECOND), "--dry-run")

        listed = run("lot", "list")

        assert "L-2024-0041" not in listed.output
        assert "L-2024-0042" not in listed.output

    def test_a_dry_run_still_reports_the_refusals(self, run, a_list) -> None:
        result = run_import(run, a_list(GOOD, TOO_HEAVY), "--dry-run")

        assert "1 would be booked in, 1 refused" in result.output

    def test_running_it_for_real_afterwards_works(self, run, a_list) -> None:
        path = a_list(GOOD, SECOND)
        run_import(run, path, "--dry-run")

        result = run_import(run, path)

        assert result.exit_code == 0
        assert "2 booked in" in result.output


class TestImportingTheSameListTwice:
    def test_the_second_run_refuses_the_lots_that_are_already_there(self, run, a_list) -> None:
        path = a_list(GOOD)
        run_import(run, path)

        result = run_import(run, path)

        assert result.exit_code == 1
        assert "0 booked in, 1 refused" in result.output
