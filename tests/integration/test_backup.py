"""Taking a copy, and checking it is one.

The interesting tests here are the ones where the copy is damaged afterwards,
because the whole reason the tool verifies is that a file which exists and has
roughly the right size is not evidence of anything.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.storage.lots import LotRepository
from arc.storage.schema import MIGRATIONS, applied_versions, connect, migrate
from arc.tools.backup import backup_to, dated_name, verify

BOOKED = date(2025, 1, 6)
TODAY = date(2025, 1, 13)


@pytest.fixture
def live(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


class TestWhatTheCopyIsCalled:
    def test_it_carries_the_day_it_was_taken(self) -> None:
        assert dated_name(TODAY) == "arc-2025-01-13.sqlite3"

    def test_a_week_of_them_sorts_by_name(self) -> None:
        names = [dated_name(date(2025, 1, day)) for day in (13, 6, 20)]

        assert sorted(names) == [
            "arc-2025-01-06.sqlite3",
            "arc-2025-01-13.sqlite3",
            "arc-2025-01-20.sqlite3",
        ]


class TestTakingACopy:
    def test_the_file_appears(self, live, tmp_path) -> None:
        result = backup_to(live, tmp_path / "backups" / dated_name(TODAY))

        assert result.path.exists()
        assert result.bytes_written > 0

    def test_the_directory_is_made_if_it_is_not_there(self, live, tmp_path) -> None:
        target = tmp_path / "somewhere" / "else" / dated_name(TODAY)

        backup_to(live, target)

        assert target.exists()

    def test_the_copy_holds_the_data(self, live, tmp_path) -> None:
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)

        copy = connect(target, journal_mode="delete")
        found = LotRepository(copy).require("L-2024-0041")
        copy.close()

        assert found.merchant == "Ravenscar Grain"
        assert found.declared_weight_kg == Decimal("24000")

    def test_the_copy_has_every_migration(self, live, tmp_path) -> None:
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)

        copy = connect(target, journal_mode="delete")
        versions = applied_versions(copy)
        copy.close()

        assert len(versions) == len(MIGRATIONS)

    def test_it_says_how_many_pages_it_moved(self, live, tmp_path) -> None:
        result = backup_to(live, tmp_path / dated_name(TODAY))

        assert result.pages_copied > 0

    def test_it_verifies_what_it_wrote(self, live, tmp_path) -> None:
        result = backup_to(live, tmp_path / dated_name(TODAY))

        assert result.verified is True
        assert "verified" in result.describe()

    def test_the_live_database_is_still_usable_afterwards(self, live, tmp_path) -> None:
        backup_to(live, tmp_path / dated_name(TODAY))

        LotRepository(live).save(make_lot(serial=42), booked_in_on=BOOKED)

        assert LotRepository(live).count() == 2


class TestNotOverwritingByAccident:
    def test_a_second_copy_on_the_same_day_is_refused(self, live, tmp_path) -> None:
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)

        with pytest.raises(FileExistsError):
            backup_to(live, target)

    def test_unless_it_is_told_to(self, live, tmp_path) -> None:
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)

        result = backup_to(live, target, overwrite=True)

        assert result.verified is True


class TestVerifying:
    def test_a_good_copy_passes(self, live, tmp_path) -> None:
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)

        assert verify(target) is True

    def test_a_file_that_is_not_a_database_fails(self, tmp_path) -> None:
        not_a_database = tmp_path / "arc-2025-01-13.sqlite3"
        not_a_database.write_text("this is a shopping list", encoding="utf-8")

        assert verify(not_a_database) is False

    def test_a_truncated_copy_fails(self, live, tmp_path) -> None:
        # Half a file is the shape a backup takes when the disk filled up
        # partway through, and it is still a file of about the right size.
        target = tmp_path / dated_name(TODAY)
        backup_to(live, target)
        whole = target.read_bytes()
        target.write_bytes(whole[: len(whole) // 2])

        assert verify(target) is False

    def test_a_database_from_an_older_release_fails(self, tmp_path) -> None:
        # It opens, it is intact, and it is missing the last two migrations,
        # so restoring it would put the station back a release without
        # anybody being told.
        old = tmp_path / "old.sqlite3"
        connection = connect(old, journal_mode="delete", synchronous="off")
        migrate(connection, tuple(m for m in MIGRATIONS if m.version <= 5))
        connection.close()

        assert verify(old) is False

    def test_an_empty_but_migrated_database_passes(self, tmp_path) -> None:
        # Nothing in it is not the same as wrong. A station on its first
        # morning has an empty database and is entitled to a backup of it.
        empty = tmp_path / "empty.sqlite3"
        connection = connect(empty, journal_mode="delete", synchronous="off")
        migrate(connection)
        connection.close()

        assert verify(empty) is True

    def test_a_file_that_is_not_there_at_all(self, tmp_path) -> None:
        assert verify(tmp_path / "never-taken.sqlite3") is False

    def test_and_asking_about_it_does_not_create_one(self, tmp_path) -> None:
        # SQLite makes a database at whatever name it is handed, so a careless
        # check would answer no and leave an empty database behind that
        # answers yes the second time.
        missing = tmp_path / "never-taken.sqlite3"

        verify(missing)

        assert missing.exists() is False
