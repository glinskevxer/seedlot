"""The two commands about the database rather than about seed.

Both are meant to be run by somebody who is not watching: doctor from a Monday
morning job, backup from a nightly one. So the exit codes matter more than the
output, and most of these are about the exit code.
"""

from __future__ import annotations

import pytest

from arc.storage.schema import connect


@pytest.fixture
def worked(run):
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


def certify(run) -> None:
    run(
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
    run(
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
    run("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")


class TestTheDoctor:
    def test_a_fresh_database_is_clean(self, run) -> None:
        result = run("doctor")

        assert result.exit_code == 0
        assert "nothing to report" in result.output

    def test_a_station_that_did_everything_right_is_clean(self, worked) -> None:
        certify(worked)

        result = worked("doctor")

        assert result.exit_code == 0

    def test_it_says_how_many_jars_are_held(self, worked) -> None:
        certify(worked)

        assert "1 samples held" in worked("doctor").output

    def test_quiet_leaves_that_off(self, worked) -> None:
        certify(worked)

        assert "samples held" not in worked("--quiet", "doctor").output

    def test_a_lot_stuck_in_test_is_reported(self, worked) -> None:
        worked(
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

        result = worked("--today", "2025-06-01", "doctor")

        assert "LOT_STUCK_IN_TEST" in result.output

    def test_and_that_alone_does_not_make_it_exit_non_zero(self, worked) -> None:
        worked(
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

        result = worked("--today", "2025-06-01", "doctor")

        assert result.exit_code == 0

    def test_a_certificate_with_no_sample_behind_it_is_serious(self, worked) -> None:
        certify(worked)
        worked(
            "store",
            "dispose",
            "L-2024-0041",
            "--force",
            "--reason",
            "spoiled in store",
        )

        result = worked("doctor")

        assert result.exit_code == 1
        assert "CERTIFICATE_WITHOUT_A_SAMPLE" in result.output


class TestTheBackup:
    def test_it_writes_a_copy_named_for_today(self, worked, tmp_path) -> None:
        target = tmp_path / "backups"

        result = worked("backup", "--to", str(target))

        assert result.exit_code == 0
        assert (target / "arc-2024-10-02.sqlite3").exists()

    def test_it_says_the_copy_was_verified(self, worked, tmp_path) -> None:
        result = worked("backup", "--to", str(tmp_path / "backups"))

        assert "verified" in result.output

    def test_the_copy_holds_the_work(self, worked, tmp_path) -> None:
        certify(worked)
        target = tmp_path / "backups"
        worked("backup", "--to", str(target))

        copy = connect(target / "arc-2024-10-02.sqlite3", journal_mode="delete")
        rows = copy.execute("select count(*) as n from certificate").fetchone()
        copy.close()

        assert rows["n"] == 1

    def test_a_second_copy_the_same_day_is_refused(self, worked, tmp_path) -> None:
        target = tmp_path / "backups"
        worked("backup", "--to", str(target))

        result = worked("backup", "--to", str(target))

        assert result.exit_code == 2
        assert "use --overwrite" in result.output

    def test_unless_it_is_told_to(self, worked, tmp_path) -> None:
        target = tmp_path / "backups"
        worked("backup", "--to", str(target))

        result = worked("backup", "--to", str(target), "--overwrite")

        assert result.exit_code == 0

    def test_a_different_day_writes_a_second_file(self, worked, tmp_path) -> None:
        target = tmp_path / "backups"
        worked("backup", "--to", str(target))

        worked("--today", "2024-10-03", "backup", "--to", str(target))

        assert len(list(target.glob("arc-*.sqlite3"))) == 2
