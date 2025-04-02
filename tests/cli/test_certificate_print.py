"""Printing a certificate from the console."""

from __future__ import annotations

import pytest

from arc.errors import NotFound

NUMBER = "GB-0214/2024/00001"


@pytest.fixture
def certified(run):
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
    return run


class TestPrintingOne:
    def test_it_comes_out_on_the_form(self, certified) -> None:
        result = certified("certificate", "print", NUMBER)

        assert result.exit_code == 0
        assert "RAVENSCAR SEED TESTING STATION" in result.output

    def test_the_figures_are_on_it(self, certified) -> None:
        result = certified("certificate", "print", NUMBER)

        assert "98.4 per cent by weight" in result.output
        assert "96 percent normal seedlings" in result.output

    def test_nothing_runs_past_the_perforation(self, certified) -> None:
        result = certified("certificate", "print", NUMBER)

        for line in result.output.splitlines():
            assert len(line) <= 78, line

    def test_a_certificate_that_was_never_issued(self, certified) -> None:
        with pytest.raises(NotFound):
            certified("certificate", "print", "GB-0214/2024/00999")


class TestPrintingALotsHistory:
    def test_every_certificate_on_the_lot(self, certified) -> None:
        certified(
            "certificate",
            "issue",
            "L-2024-0041",
            "--signed-by",
            "A. Pearce",
            "--kind",
            "green",
        )

        result = certified("certificate", "print", "--lot", "L-2024-0041")

        assert "GB-0214/2024/00001" in result.output
        assert "GB-0214/2024/00002" in result.output

    def test_they_are_separated_for_the_printer(self, certified) -> None:
        certified(
            "certificate",
            "issue",
            "L-2024-0041",
            "--signed-by",
            "A. Pearce",
            "--kind",
            "green",
        )

        result = certified("certificate", "print", "--lot", "L-2024-0041")

        assert "\f" in result.output

    def test_a_lot_with_nothing_issued_on_it(self, run) -> None:
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

        result = run("certificate", "print", "--lot", "L-2024-0042")

        assert result.exit_code == 2
        assert "nothing has been issued" in result.output


class TestSayingWhichOne:
    def test_neither_a_number_nor_a_lot_is_refused(self, certified) -> None:
        result = certified("certificate", "print")

        assert result.exit_code != 0
        assert "either a certificate number or --lot" in result.output

    def test_both_at_once_is_refused_too(self, certified) -> None:
        result = certified("certificate", "print", NUMBER, "--lot", "L-2024-0041")

        assert result.exit_code != 0


class TestWritingItToAFile:
    def test_the_file_is_written(self, certified, tmp_path) -> None:
        target = tmp_path / "cert.txt"

        result = certified("certificate", "print", NUMBER, "--out", str(target))

        assert result.exit_code == 0
        assert target.exists()

    def test_and_holds_the_form(self, certified, tmp_path) -> None:
        target = tmp_path / "cert.txt"
        certified("certificate", "print", NUMBER, "--out", str(target))

        written = target.read_text(encoding="utf-8")

        assert "GB-0214/2024/00001" in written
        assert "L-2024-0041" in written

    def test_the_terminal_stays_quiet(self, certified, tmp_path) -> None:
        target = tmp_path / "cert.txt"

        result = certified("certificate", "print", NUMBER, "--out", str(target))

        assert "RAVENSCAR" not in result.output
