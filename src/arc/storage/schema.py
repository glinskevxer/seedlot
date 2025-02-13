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
    Migration(
        version=4,
        name="moisture and seed weight",
        statements=(
            """
            create table moisture_determination (
                id               integer primary key autoincrement,
                lot_reference    text not null references lot (reference),
                container_g      text not null,
                with_sample_g    text not null,
                after_drying_g   text not null,
                percent          text not null,
                stage            text not null,
                combined_percent text,
                analyst          text not null,
                determined_on    text not null,
                constraint moisture_stage_ck check (stage in ('single', 'predry', 'second'))
            )
            """,
            "create index moisture_lot_idx on moisture_determination (lot_reference)",
            """
            create table seed_weight (
                id             integer primary key autoincrement,
                lot_reference  text not null references lot (reference),
                mean_g         text not null,
                deviation_g    text not null,
                variation      text not null,
                limit_applied  text not null,
                grams_per_thousand text not null,
                analyst        text not null,
                determined_on  text not null
            )
            """,
            """
            create table seed_weight_replicate (
                id              integer primary key autoincrement,
                seed_weight_id  integer not null
                    references seed_weight (id) on delete cascade,
                position        integer not null,
                weight_g        text not null,
                unique (seed_weight_id, position)
            )
            """,
            "create index seed_weight_lot_idx on seed_weight (lot_reference)",
        ),
    ),
    Migration(
        version=5,
        name="other seed searches",
        statements=(
            """
            create table other_seed_search (
                id              integer primary key autoincrement,
                lot_reference   text not null references lot (reference),
                species_name    text not null,
                kind            text not null,
                weight_examined_g text not null,
                sought          text not null default '',
                analyst         text not null,
                searched_on     text not null,
                constraint other_seed_kind_ck
                    check (kind in ('complete', 'limited', 'reduced'))
            )
            """,
            """
            create table other_seed_finding (
                id           integer primary key autoincrement,
                search_id    integer not null
                    references other_seed_search (id) on delete cascade,
                species_name text not null,
                count        integer not null,
                constraint other_seed_count_ck check (count >= 0),
                unique (search_id, species_name)
            )
            """,
            "create index other_seed_lot_idx on other_seed_search (lot_reference)",
        ),
    ),
    Migration(
        version=6,
        name="dormancy treatment on a germination test",
        statements=(
            # Existing rows are tests that had nothing done to the sample,
            # which is exactly what the default says, so no backfill is needed.
            "alter table germination_test add column treatment text not null " "default 'none'",
            "create index germination_treatment_idx on germination_test (treatment)",
        ),
    ),
    Migration(
        version=7,
        name="retained samples and what has been drawn from them",
        statements=(
            """
            create table retained_sample (
                lot_reference    text primary key references lot (reference),
                species_name     text not null,
                remaining_g      text not null,
                held_from        text not null,
                certificate_kind text,
                disposed_on      text,
                disposal_reason  text,
                constraint disposal_has_a_reason_ck check (
                    (disposed_on is null and disposal_reason is null)
                    or (disposed_on is not null and disposal_reason is not null)
                )
            )
            """,
            """
            create table retained_draw (
                id            integer primary key autoincrement,
                lot_reference text not null references retained_sample (lot_reference),
                determination text not null,
                weight_g      text not null,
                drawn_on      text not null,
                analyst       text not null
            )
            """,
            "create index retained_draw_lot_idx on retained_draw (lot_reference)",
            """
            create index retained_held_idx on retained_sample (held_from)
                where disposed_on is null
            """,
        ),
    ),
    Migration(
        version=8,
        name="referee comparisons against another laboratory",
        statements=(
            """
            create table referee_comparison (
                id                 integer primary key autoincrement,
                lot_reference      text not null references lot (reference),
                certificate_number text not null,
                determination      text not null,
                ours               text not null,
                theirs             text not null,
                allowance          text not null,
                verdict            text not null,
                other_laboratory   text not null,
                raised_by          text not null,
                compared_on        text not null,
                constraint referee_verdict_ck check (verdict in ('agree', 'refer')),
                constraint referee_determination_ck
                    check (determination in ('purity', 'germination'))
            )
            """,
            """
            create index referee_lot_idx
                on referee_comparison (lot_reference, compared_on)
            """,
            """
            create index referee_certificate_idx
                on referee_comparison (certificate_number)
            """,
        ),
    ),
)


def connect(
    path: Path | str,
    *,
    journal_mode: str = "wal",
    synchronous: str = "full",
) -> sqlite3.Connection:
    """Opens the database with the settings the station relies on.

    Foreign keys are off by default in SQLite, which means a reference to a lot
    that does not exist is accepted quietly. Everything here assumes they are
    on, so they are turned on for every connection rather than hoped for.

    The journal mode is a parameter because the two callers want different
    things from it. The station wants write ahead logging: the file is on a
    share, two people have the console open, and a power cut in the middle of
    a certificate must not take the database with it. A test wants a database
    that lives for four milliseconds and does not need to survive anything, and
    setting up the log costs more than every query the test then runs.

    Synchronous is the same argument and a much larger effect. On full, every
    commit waits for the disk to say it is done, which is what a station whose
    certificates are in this file wants and is most of the time a migration
    takes. Turning it off makes a throwaway database around seventy times
    faster to build and makes a power cut during a write unrecoverable, so it
    belongs on databases nobody would miss and nowhere else.
    """
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    connection.execute(f"pragma journal_mode = {journal_mode}")
    connection.execute(f"pragma synchronous = {synchronous}")
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


def migrate(
    connection: sqlite3.Connection,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> tuple[int, ...]:
    """Brings the database up to date and says what it applied.

    Each migration runs in its own transaction. A migration that fails halfway
    leaves the ones before it applied and itself not, which is the only state
    that can be recovered from without guessing.

    The list is a parameter so that a test can build a database as an older
    release left it and then let the newer migrations run over it. That is the
    case that breaks in production and never in a suite, because a suite always
    migrates from empty.
    """
    already = set(applied_versions(connection))
    applied: list[int] = []

    for migration in migrations:
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
