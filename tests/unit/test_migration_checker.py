"""The check that guards the migration list.

The checker exists to catch a numbering mistake before it reaches a database
that already holds real certificates, so these tests hand it broken lists on
purpose and make sure it says which one is broken and why.
"""

from __future__ import annotations

import pytest

from arc.storage.schema import MIGRATIONS, Migration
from arc.tools import check_migrations


@pytest.fixture
def swap(monkeypatch: pytest.MonkeyPatch):
    """Puts a made up migration list in front of the checker."""

    def replace(migrations: tuple[Migration, ...]) -> None:
        monkeypatch.setattr(check_migrations, "MIGRATIONS", migrations)

    return replace


def a_migration(version: int, name: str = "does something") -> Migration:
    return Migration(version=version, name=name, statements=("select 1",))


class TestTheRealList:
    def test_the_migrations_that_ship_are_fine(self) -> None:
        assert check_migrations.problems() == []

    def test_and_there_are_some(self) -> None:
        # A checker that passes an empty list would pass anything.
        assert len(MIGRATIONS) >= 4

    def test_the_program_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert check_migrations.main() == 0
        assert str(len(MIGRATIONS)) in capsys.readouterr().out


class TestNumbering:
    def test_a_version_used_twice_is_caught(self, swap) -> None:
        swap((a_migration(1), a_migration(2), a_migration(2)))

        found = check_migrations.problems()

        assert any("more than once" in problem for problem in found)

    def test_out_of_order_is_caught(self, swap) -> None:
        swap((a_migration(1), a_migration(3), a_migration(2)))

        found = check_migrations.problems()

        assert any("version order" in problem for problem in found)

    def test_a_gap_is_caught(self, swap) -> None:
        # Numbering 1, 2, 4 leaves a database that has taken 1 and 2 unable to
        # say whether it is missing 3 or whether 3 never existed.
        swap((a_migration(1), a_migration(2), a_migration(4)))

        found = check_migrations.problems()

        assert any("expected versions" in problem for problem in found)

    def test_starting_at_zero_is_caught(self, swap) -> None:
        swap((a_migration(0), a_migration(1)))

        assert check_migrations.problems() != []


class TestContent:
    def test_a_migration_that_does_nothing_is_caught(self, swap) -> None:
        swap((Migration(version=1, name="empty", statements=()),))

        found = check_migrations.problems()

        assert any("does nothing" in problem for problem in found)

    def test_a_migration_with_no_name_is_caught(self, swap) -> None:
        swap((a_migration(1, name="   "),))

        found = check_migrations.problems()

        assert any("does not say what it is for" in problem for problem in found)

    def test_the_problems_come_back_in_the_order_they_were_found(self, swap) -> None:
        swap((a_migration(2, name=""),))

        found = check_migrations.problems()

        assert len(found) == 2
        assert "expected versions" in found[0]
        assert "does not say what it is for" in found[1]


class TestTheProgram:
    def test_a_broken_list_exits_non_zero(
        self, swap, capsys: pytest.CaptureFixture[str]
    ) -> None:
        swap((a_migration(1), a_migration(1)))

        code = check_migrations.main()

        assert code == 1
        assert "more than once" in capsys.readouterr().err

    def test_the_complaint_goes_to_standard_error(
        self, swap, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # CI reads the exit code, but the person reading the log needs the
        # reason to be somewhere that is not swallowed by a pipe.
        swap((a_migration(1), a_migration(3)))

        check_migrations.main()
        captured = capsys.readouterr()

        assert captured.out == ""
        assert captured.err.strip() != ""
