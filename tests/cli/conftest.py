"""Running the command line the way a person would."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from arc.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def run(runner, tmp_path):
    """Runs a command against a database of its own and returns the result."""

    def invoke(*args: str):
        return runner.invoke(
            cli,
            ["--database", str(tmp_path / "arc.sqlite3"), *args],
            catch_exceptions=False,
        )

    return invoke
