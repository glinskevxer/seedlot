"""How a connection is opened, which is not a detail.

Two of these settings are load bearing and neither of them is on by default.
Foreign keys off means a determination can be written against a lot reference
that does not exist and nothing complains until somebody goes looking for the
lot. And the journal mode is the difference between a suite that runs in
fifteen seconds and one that runs in fifty, because setting up a write ahead
log costs more than every query a short test then makes.
"""

from __future__ import annotations

import sqlite3

import pytest

from arc.storage.schema import MIGRATIONS, applied_versions, connect, migrate


def journal_mode(connection: sqlite3.Connection) -> str:
    return str(connection.execute("pragma journal_mode").fetchone()[0]).lower()


def foreign_keys_on(connection: sqlite3.Connection) -> bool:
    return bool(connection.execute("pragma foreign_keys").fetchone()[0])


class TestWhatEveryConnectionGets:
    def test_foreign_keys_are_turned_on(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3")

        assert foreign_keys_on(connection) is True

        connection.close()

    def test_rows_come_back_by_name(self, tmp_path) -> None:
        # Every repository reads row["column"], which is a TypeError on the
        # tuples SQLite hands back without this.
        connection = connect(tmp_path / "arc.sqlite3")

        row = connection.execute("select 1 as answer").fetchone()

        assert row["answer"] == 1

        connection.close()

    def test_it_is_not_wrapped_in_an_implicit_transaction(self, tmp_path) -> None:
        # The repositories open their own transactions where they need one.
        connection = connect(tmp_path / "arc.sqlite3")

        assert connection.isolation_level is None

        connection.close()


class TestTheJournalMode:
    def test_the_station_gets_the_write_ahead_log(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3")

        assert journal_mode(connection) == "wal"

        connection.close()

    def test_a_test_database_can_ask_for_something_cheaper(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")

        assert journal_mode(connection) == "memory"

        connection.close()

    def test_the_cheaper_one_still_holds_the_data(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")
        migrate(connection)

        connection.execute("create table scratch (value text)")
        connection.execute("insert into scratch values ('kept')")

        assert connection.execute("select value from scratch").fetchone()[0] == "kept"

        connection.close()

    def test_and_still_enforces_foreign_keys(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")
        migrate(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "insert into submitted_sample "
                "(lot_reference, weight_g, received_on, seal_intact, reduction_method) "
                "values ('L-2024-9999', '1000', '2024-09-18', 1, 'divider')"
            )

        connection.close()


class TestMigrating:
    def test_an_empty_database_takes_every_migration(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")

        applied = migrate(connection)

        assert len(applied) == len(MIGRATIONS)

        connection.close()

    def test_running_it_again_applies_nothing(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")
        migrate(connection)

        assert migrate(connection) == ()

        connection.close()

    def test_the_versions_are_recorded_in_order(self, tmp_path) -> None:
        connection = connect(tmp_path / "arc.sqlite3", journal_mode="memory")
        migrate(connection)

        versions = applied_versions(connection)

        assert list(versions) == sorted(versions)
        assert versions[0] == 1

        connection.close()

    def test_a_second_connection_sees_the_migrated_schema(self, tmp_path) -> None:
        path = tmp_path / "arc.sqlite3"
        first = connect(path, journal_mode="memory")
        migrate(first)
        first.close()

        second = connect(path, journal_mode="memory")

        assert applied_versions(second) == applied_versions(connect(path))

        second.close()
