"""Disputing a result, from the console.

Every test here needs a certificate to dispute, so the fixture runs the whole
job first. The certificate number is the one the station issues for the first
certificate of 2024, which is what makes it predictable enough to type into a
test.
"""

from __future__ import annotations

import pytest

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


def compare(run, theirs: str, *, determination: str = "germination", certificate=NUMBER):
    return run(
        "referee",
        "compare",
        "L-2024-0041",
        "--certificate",
        certificate,
        "--for",
        determination,
        "--theirs",
        theirs,
        "--laboratory",
        "NL-0510 Wageningen",
        "--raised-by",
        "Ravenscar Grain",
    )


class TestComparingAGermination:
    def test_two_results_that_agree(self, certified) -> None:
        result = compare(certified, "94")

        assert result.exit_code == 0
        assert "the first result stands" in result.output

    def test_the_output_carries_both_numbers_and_the_allowance(self, certified) -> None:
        result = compare(certified, "94")

        assert "we reported 96 and they reported 94" in result.output
        assert "allowed between laboratories" in result.output

    def test_two_that_do_not_agree_exit_non_zero(self, certified) -> None:
        result = compare(certified, "80")

        assert result.exit_code == 1
        assert "refer the lot to a third laboratory" in result.output

    def test_the_comparison_is_recorded_either_way(self, certified) -> None:
        compare(certified, "80")

        shown = certified("referee", "show", "L-2024-0041")

        assert "NL-0510 Wageningen" in shown.output
        assert "Ravenscar Grain" in shown.output


class TestComparingAPurity:
    def test_two_analyses_that_agree(self, certified) -> None:
        result = compare(certified, "98.2", determination="purity")

        assert result.exit_code == 0
        assert "we reported 98.4 and they reported 98.2" in result.output

    def test_two_that_are_far_apart(self, certified) -> None:
        result = compare(certified, "91.0", determination="purity")

        assert result.exit_code == 1

    def test_a_percentage_that_is_not_a_number(self, certified) -> None:
        result = compare(certified, "quite pure", determination="purity")

        assert result.exit_code != 0


class TestWhatIsRefused:
    def test_a_certificate_issued_against_another_lot(self, certified) -> None:
        certified(
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
        result = certified(
            "referee",
            "compare",
            "L-2024-0042",
            "--certificate",
            NUMBER,
            "--for",
            "germination",
            "--theirs",
            "94",
            "--laboratory",
            "NL-0510 Wageningen",
            "--raised-by",
            "Ravenscar Grain",
        )

        assert result.exit_code != 0
        assert "was issued against L-2024-0041" in result.output

    def test_a_determination_that_is_not_refereed(self, certified) -> None:
        result = compare(certified, "14.0", determination="moisture")

        assert result.exit_code != 0


class TestReadingThemBack:
    def test_a_lot_nobody_disputed(self, certified) -> None:
        shown = certified("referee", "show", "L-2024-0041")

        assert "nothing has been disputed" in shown.output

    def test_an_empty_disputed_list(self, certified) -> None:
        compare(certified, "94")

        assert "nothing outstanding" in certified("referee", "disputed").output

    def test_a_disagreement_shows_up_on_the_disputed_list(self, certified) -> None:
        compare(certified, "80")

        listed = certified("referee", "disputed")

        assert "L-2024-0041" in listed.output
        assert "third laboratory" in listed.output

    def test_both_comparisons_show_against_the_lot(self, certified) -> None:
        compare(certified, "94")
        compare(certified, "98.2", determination="purity")

        shown = certified("referee", "show", "L-2024-0041")

        assert "germination" in shown.output
        assert "purity" in shown.output
        assert "2." in shown.output
