"""The database, and the migrations that get it there.

SQLite, because the station is one building with four analysts in it and a
server would be a thing to maintain rather than a thing that helps. The file
sits on the share and is backed up with everything else.

Migrations are numbered and applied in order, and none of them is ever edited
once it has run anywhere. The pattern is the same one every project arrives at
eventually, written out here rather than pulled in, because the whole of it is
sixty lines and a dependency would be larger than the thing it replaces.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Migration", "MIGRATIONS", "connect", "migrate", "applied_versions"]


@dataclass(frozen=True)
class Migration:
    """One numbered step, applied once and never changed afterwards."""

    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="lots and samples",
        statements=(
            """
            create table lot (
                reference        text primary key,
                species_name     text not null,
                declared_weight_kg  text not null,
                container_kind   text not null,
                container_count  integer not null,
                merchant         text not null,
                sealed_on        text not null,
                origin_country   text not null,
                status           text not null,
                sublot_of        text references lot (reference),
                notes            text not null default '',
                booked_in_at     text not null
            )
            """,
            "create index lot_species_idx on lot (species_name)",
            "create index lot_open_idx on lot (status) where status <> 'closed'",
            """
            create table submitted_sample (
                id               integer primary key autoincrement,
                lot_reference    text not null references lot (reference),
                weight_g         text not null,
                received_on      text not null,
                seal_intact      integer not null,
                reduction_method text not null,
                sampler          text not null,
                notes            text not null default ''
            )
            """,
            "create index submitted_sample_lot_idx on submitted_sample (lot_reference)",
        ),
    ),
    Migration(
        version=2,
        name="determinations",
        statements=(
            """
            create table purity_analysis (
                id                 integer primary key autoincrement,
                lot_reference      text not null references lot (reference),
                working_sample_g   text not null,
                pure_seed_g        text not null,
                other_seed_g       text not null,
                inert_matter_g     text not null,
                pure_seed_percent  text,
                other_seed_percent text,
                inert_percent      text,
                analyst            text not null,
                analysed_on        text not null,
                is_duplicate       integer not null default 0
            )
            """,
            "create index purity_lot_idx on purity_analysis (lot_reference)",
            """
            create table germination_test (
                id                integer primary key autoincrement,
                lot_reference     text not null references lot (reference),
                seeds_per_replicate integer not null,
                replicate_count   integer not null,
                set_down_on       text not null,
                final_count_on    text not null,
                analyst           text not null,
                is_retest         integer not null default 0,
                mean_normal       integer,
                replicate_range   text
            )
            """,
            """
            create table germination_replicate (
                id        integer primary key autoincrement,
                test_id   integer not null references germination_test (id) on delete cascade,
                position  integer not null,
                normal    integer not null,
                abnormal  integer not null,
                hard      integer not null,
                fresh     integer not null,
                dead      integer not null,
                unique (test_id, position)
            )
            """,
            "create index germination_lot_idx on germination_test (lot_reference)",
        ),
    ),
    Migration(
        version=3,
        name="certificates",
        statements=(
            """
            create table certificate (
                number            text primary key,
                kind              text not null,
                lot_reference     text not null references lot (reference),
                species_name      text not null,
                merchant          text not null,
                origin_country    text not null,
                lot_weight_kg     text not null,
                issued_on         text not null,
                signed_by         text not null,
                supersedes        text references certificate (number),
                withdrawn_on      text,
                results_json      text not null
            )
            """,
            "create index certificate_lot_idx on certificate (lot_reference)",
            """
            create index certificate_live_idx on certificate (issued_on)
            where withdrawn_on is null
            """,
        ),
    ),
)


def connect(path: Path | str) -> sqlite3.Connection:
    """Opens the database with the settings the station relies on.

    Foreign keys are off by default in SQLite, which means a reference to a lot
    that does not exist is accepted quietly. Everything here assumes they are
    on, so they are turned on for every connection rather than hoped for.
    """
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma journal_mode = wal")
    return connection


def applied_versions(connection: sqlite3.Connection) -> tuple[int, ...]:
    """Which migrations this database has had, oldest first."""
    connection.execute(
        """
        create table if not exists schema_migration (
            version    integer primary key,
            name       text not null,
            applied_at text not null default current_timestamp
        )
        """
    )
    rows = connection.execute(
        "select version from schema_migration order by version"
    ).fetchall()
    return tuple(row["version"] for row in rows)


def migrate(connection: sqlite3.Connection) -> tuple[int, ...]:
    """Brings the database up to date and says what it applied.

    Each migration runs in its own transaction. A migration that fails halfway
    leaves the ones before it applied and itself not, which is the only state
    that can be recovered from without guessing.
    """
    already = set(applied_versions(connection))
    applied: list[int] = []

    for migration in MIGRATIONS:
        if migration.version in already:
            continue
        connection.execute("begin")
        try:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "insert into schema_migration (version, name) values (?, ?)",
                (migration.version, migration.name),
            )
            connection.execute("commit")
        except Exception:
            connection.execute("rollback")
            raise
        applied.append(migration.version)

    return tuple(applied)
