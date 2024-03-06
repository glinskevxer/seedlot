"""The migrations, against a real database.

Nothing here is mocked. A schema that only works against a fake is a schema
nobody has run.
"""

from __future__ import annotations

import sqlite3

import pytest

from arc.storage.schema import MIGRATIONS, applied_versions, connect, migrate


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "arc.sqlite3")
    yield connection
    connection.close()


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "select name from sqlite_master where type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


class TestTheMigrationsThemselves:
    def test_they_are_numbered_from_one_without_gaps(self) -> None:
        versions = [migration.version for migration in MIGRATIONS]

        assert versions == list(range(1, len(MIGRATIONS) + 1))

    def test_every_migration_says_what_it_is_for(self) -> None:
        for migration in MIGRATIONS:
            assert migration.name
            assert migration.statements

    def test_no_version_is_used_twice(self) -> None:
        versions = [migration.version for migration in MIGRATIONS]

        assert len(set(versions)) == len(versions)


class TestApplyingThem:
    def test_an_empty_database_gets_all_of_them(self, db) -> None:
        applied = migrate(db)

        assert applied == tuple(migration.version for migration in MIGRATIONS)

    def test_the_tables_the_station_needs_are_there_afterwards(self, db) -> None:
        migrate(db)

        assert {
            "lot",
            "submitted_sample",
            "purity_analysis",
            "germination_test",
            "germination_replicate",
            "certificate",
        } <= table_names(db)

    def test_running_them_again_does_nothing(self, db) -> None:
        migrate(db)

        assert migrate(db) == ()

    def test_the_history_records_what_was_applied(self, db) -> None:
        migrate(db)

        assert applied_versions(db) == tuple(m.version for m in MIGRATIONS)

    def test_a_database_part_way_up_only_gets_what_it_is_missing(self, db) -> None:
        applied_versions(db)
        db.execute(
            "insert into schema_migration (version, name) values (1, 'lots and samples')"
        )
        db.execute(MIGRATIONS[0].statements[0])
        db.execute(MIGRATIONS[0].statements[3])

        applied = migrate(db)

        assert 1 not in applied
        assert applied == (2, 3)


class TestWhatTheConnectionGuarantees:
    def test_foreign_keys_are_on(self, db) -> None:
        assert db.execute("pragma foreign_keys").fetchone()[0] == 1

    def test_a_reference_to_a_lot_that_does_not_exist_is_refused(self, db) -> None:
        migrate(db)

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into submitted_sample
                    (lot_reference, weight_g, received_on, seal_intact,
                     reduction_method, sampler)
                values ('L-2024-9999', '1000', '2024-09-18', 1, 'mechanical divider', 'R. A.')
                """
            )

    def test_rows_come_back_addressable_by_column_name(self, db) -> None:
        migrate(db)
        db.execute(
            """
            insert into lot (reference, species_name, declared_weight_kg, container_kind,
                             container_count, merchant, sealed_on, origin_country,
                             status, booked_in_at)
            values ('L-2024-0041', 'Triticum aestivum', '24000', 'bag', 480,
                    'Ravenscar Grain', '2024-09-12', 'GB', 'booked in', '2024-09-18')
            """
        )

        row = db.execute("select * from lot").fetchone()

        assert row["reference"] == "L-2024-0041"
        assert row["species_name"] == "Triticum aestivum"

    def test_deleting_a_test_takes_its_replicates_with_it(self, db) -> None:
        migrate(db)
        db.execute(
            """
            insert into lot (reference, species_name, declared_weight_kg, container_kind,
                             container_count, merchant, sealed_on, origin_country,
                             status, booked_in_at)
            values ('L-2024-0041', 'Triticum aestivum', '24000', 'bag', 480,
                    'Ravenscar Grain', '2024-09-12', 'GB', 'booked in', '2024-09-18')
            """
        )
        db.execute(
            """
            insert into germination_test (id, lot_reference, seeds_per_replicate,
                                          replicate_count, set_down_on, final_count_on, analyst)
            values (1, 'L-2024-0041', 100, 4, '2024-09-20', '2024-09-28', 'J. W.')
            """
        )
        db.execute(
            """
            insert into germination_replicate (test_id, position, normal, abnormal,
                                               hard, fresh, dead)
            values (1, 1, 96, 2, 0, 1, 1)
            """
        )

        db.execute("delete from germination_test where id = 1")

        assert db.execute("select count(*) from germination_replicate").fetchone()[0] == 0

    def test_the_same_replicate_position_cannot_be_recorded_twice(self, db) -> None:
        migrate(db)
        db.execute(
            """
            insert into lot (reference, species_name, declared_weight_kg, container_kind,
                             container_count, merchant, sealed_on, origin_country,
                             status, booked_in_at)
            values ('L-2024-0041', 'Triticum aestivum', '24000', 'bag', 480,
                    'Ravenscar Grain', '2024-09-12', 'GB', 'booked in', '2024-09-18')
            """
        )
        db.execute(
            """
            insert into germination_test (id, lot_reference, seeds_per_replicate,
                                          replicate_count, set_down_on, final_count_on, analyst)
            values (1, 'L-2024-0041', 100, 4, '2024-09-20', '2024-09-28', 'J. W.')
            """
        )
        db.execute(
            """
            insert into germination_replicate (test_id, position, normal, abnormal,
                                               hard, fresh, dead)
            values (1, 1, 96, 2, 0, 1, 1)
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into germination_replicate (test_id, position, normal, abnormal,
                                                   hard, fresh, dead)
                values (1, 1, 95, 3, 0, 1, 1)
                """
            )
