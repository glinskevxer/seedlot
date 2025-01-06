"""Opening everything a command needs off one connection.

Every command wants some combination of the four repositories and they all have
to share a connection: two connections to the same SQLite file will deadlock
each other the moment one of them is inside a transaction. So the bundle is
built once per command rather than per repository.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import click

from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository
from arc.storage.physical import MoistureRepository, SeedWeightRepository
from arc.storage.schema import connect, migrate

__all__ = ["Station", "open_station", "weight_option"]


@dataclass
class Station:
    """The station's database, opened and migrated."""

    connection: sqlite3.Connection
    lots: LotRepository
    purity: PurityRepository
    germination: GerminationRepository
    moisture: MoistureRepository
    seed_weight: SeedWeightRepository
    other_seed: OtherSeedRepository
    certificates: CertificateRepository

    def close(self) -> None:
        self.connection.close()


def open_station(
    database: Path,
    *,
    journal_mode: str = "wal",
    synchronous: str = "full",
) -> Station:
    """Opens the database, bringing it up to date if it is behind.

    Migrating on open rather than through a separate command is deliberate. The
    station has no operations team; the first person in on Monday should not
    have to know that a release needed a schema step.

    The journal mode is here rather than fixed because write ahead logging
    needs a filesystem that can do proper file locking, and the share the
    database lives on is not always one. On a mount that cannot, WAL either
    refuses quietly and falls back or corrupts the file, and neither is
    something to find out about during an audit.
    """
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database, journal_mode=journal_mode, synchronous=synchronous)
    migrate(connection)

    return Station(
        connection=connection,
        lots=LotRepository(connection),
        purity=PurityRepository(connection),
        germination=GerminationRepository(connection),
        moisture=MoistureRepository(connection),
        seed_weight=SeedWeightRepository(connection),
        other_seed=OtherSeedRepository(connection),
        certificates=CertificateRepository(connection),
    )


def weight_option(raw: str, what: str = "weight") -> Decimal:
    """Reads a weight off the command line, keeping the places it was typed to.

    Going through Decimal rather than float is the whole point: a purity
    analysis typed as 118.2 has to stay 118.2, and click's float option would
    make it 118.19999999999999 before anything got a chance to weigh it.
    """
    try:
        return Decimal(raw)
    except InvalidOperation as error:
        raise click.BadParameter(f"{raw!r} is not a {what}") from error
