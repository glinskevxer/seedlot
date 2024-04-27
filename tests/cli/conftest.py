"""Running the command line the way a person would."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from arc.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


#: The day the command line tests pretend it is. Fixed, because a certificate
#: number carries the year and a suite that changes answer on new year's eve is
#: a suite somebody has to come in and fix on new year's day.
TODAY = "2024-10-02"


@pytest.fixture
def run(runner, tmp_path):
    """Runs a command against a database of its own and returns the result."""

    def invoke(*args: str):
        return runner.invoke(
            cli,
            [
                "--database",
                str(tmp_path / "arc.sqlite3"),
                "--today",
                TODAY,
                *args,
            ],
            catch_exceptions=False,
        )

    return invoke
