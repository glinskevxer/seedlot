"""Opening the database once, and closing it afterwards.

Neither of these is visible in any command's output, which is exactly why they
are worth a test. A second connection to the same SQLite file blocks the first
the moment one of them is in a transaction, and that only shows up when the
machine is busy.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from arc.cli import station as station_module
from arc.cli.context import Context


@pytest.fixture
def counted(monkeypatch, tmp_path):
    """A context that counts how many times it really opened the database."""
    opens: list[Path] = []
    real = station_module.open_station

    def counting(database, **kwargs):
        opens.append(database)
        return real(database, **kwargs)

    monkeypatch.setattr("arc.cli.context.open_station", counting)

    context = Context(
        database=tmp_path / "arc.sqlite3",
        quiet=False,
        today=date(2024, 10, 2),
        journal_mode="memory",
        synchronous="off",
        operator="jwhitfield",
    )
    return context, opens


class TestOpeningItOnce:
    def test_the_first_call_opens_it(self, counted) -> None:
        context, opens = counted

        context.station()

        assert len(opens) == 1

    def test_the_second_call_does_not(self, counted) -> None:
        context, opens = counted

        first = context.station()
        second = context.station()

        assert first is second
        assert len(opens) == 1

    def test_five_calls_still_one_connection(self, counted) -> None:
        context, opens = counted

        connections = {id(context.station().connection) for _ in range(5)}

        assert len(connections) == 1
        assert len(opens) == 1

    def test_a_context_that_never_asks_never_opens_it(self, counted, tmp_path) -> None:
        # Commands that only print help or the station name should not create
        # a database file as a side effect.
        context, opens = counted

        context.say("nothing to do here")

        assert opens == []
        assert not (tmp_path / "arc.sqlite3").exists()


class TestClosingIt:
    def test_closing_shuts_the_connection(self, counted) -> None:
        context, _ = counted
        opened = context.station()

        context.close()

        with pytest.raises(sqlite3.ProgrammingError):
            opened.connection.execute("select 1")

    def test_closing_twice_is_harmless(self, counted) -> None:
        context, _ = counted
        context.station()

        context.close()
        context.close()

    def test_closing_one_that_was_never_opened_is_harmless(self, counted) -> None:
        context, opens = counted

        context.close()

        assert opens == []

    def test_asking_again_after_closing_opens_a_fresh_one(self, counted) -> None:
        context, opens = counted
        first = context.station()
        context.close()

        second = context.station()

        assert second is not first
        assert len(opens) == 2


class TestTheCommandLineClosesUp:
    def test_a_command_leaves_nothing_open(self, run, tmp_path) -> None:
        # click closes the context when the command finishes, and the callback
        # registered against it is what shuts the database.
        result = run("station")

        assert result.exit_code == 0

    def test_a_refused_command_closes_it_too(self, run) -> None:
        result = run(
            "lot",
            "book-in",
            "L-2024-0041",
            "--species",
            "moon dust",
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
            catch_exceptions=True,
        )

        assert result.exit_code != 0
