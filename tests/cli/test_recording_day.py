"""Recording work against the day it was done rather than the day it was typed.

The bench sheets come upstairs in a pile. Somebody types Friday's purity
analyses on Monday morning, and if the console stamps them Monday then the
certificate says the sample was analysed three days after it was reported. So
every command takes its idea of today from one option, and these tests use the
runner directly rather than the shared fixture because the point is what
happens when the option is given and when it is left out.
"""

from __future__ import annotations

from datetime import date

import pytest
from click.testing import CliRunner

from arc.cli.main import cli


@pytest.fixture
def console(tmp_path):
    """Runs commands against a database of this test's own."""
    runner = CliRunner()
    database = str(tmp_path / "arc.sqlite3")

    def invoke(*args: str):
        return runner.invoke(cli, ["--database", database, *args], catch_exceptions=False)

    return invoke


def book_in(console, *extra: str):
    return console(
        *extra,
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
        "2024-04-12",
        "--origin",
        "GB",
    )


def record_purity(console, *extra: str):
    return console(
        *extra,
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


class TestTheDayTheWorkWasDone:
    def test_an_analysis_is_stamped_with_the_day_that_was_given(self, console) -> None:
        book_in(console, "--today", "2024-05-14")
        record_purity(console, "--today", "2024-05-14")

        shown = console("purity", "show", "L-2024-0041")

        assert "2024-05-14" in shown.output

    def test_and_not_with_the_day_it_was_typed(self, console) -> None:
        book_in(console, "--today", "2024-05-14")
        record_purity(console, "--today", "2024-05-14")

        shown = console("purity", "show", "L-2024-0041")

        assert str(date.today()) not in shown.output

    def test_leaving_it_out_falls_back_to_the_real_today(self, console) -> None:
        book_in(console)
        record_purity(console)

        shown = console("purity", "show", "L-2024-0041")

        assert str(date.today()) in shown.output

    def test_two_analyses_can_be_typed_up_on_different_days(self, console) -> None:
        book_in(console, "--today", "2024-05-14")
        record_purity(console, "--today", "2024-05-14")
        record_purity(console, "--today", "2024-05-16")

        shown = console("purity", "show", "L-2024-0041")

        assert "2024-05-14" in shown.output
        assert "2024-05-16" in shown.output


class TestWhatTheOptionWillAccept:
    def test_a_date_that_is_not_a_date_is_refused(self, console) -> None:
        result = console("--today", "the fourteenth", "species", "show", "wheat")

        assert result.exit_code != 0

    def test_the_wrong_way_round_is_refused(self, console) -> None:
        # 14/05/2024 is how the paperwork is written and is not what the
        # option takes, so it has to fail loudly rather than be guessed at.
        result = console("--today", "14/05/2024", "species", "show", "wheat")

        assert result.exit_code != 0

    def test_the_option_goes_before_the_command(self, console) -> None:
        result = console("--today", "2024-05-14", "species", "show", "wheat")

        assert result.exit_code == 0
        assert "Triticum aestivum" in result.output
