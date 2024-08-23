"""Reading and writing seed lots."""

from __future__ import annotations

import sqlite3
from datetime import date

from arc.errors import NotFound
from arc.lots.model import ContainerKind, LotReference, LotStatus, SeedLot
from arc.storage.codec import (
    to_date,
    to_decimal,
    to_enum,
    to_iso,
    to_text,
)

__all__ = ["LotRepository"]


class LotRepository:
    """Seed lots, kept in the station's database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, lot: SeedLot, *, booked_in_on: date) -> SeedLot:
        """Writes a lot, or updates one that is already there.

        The reference is the key rather than a generated id, because that is
        what people say on the phone and what is written on the bag.
        """
        self._connection.execute(
            """
            insert into lot (reference, species_name, declared_weight_kg, container_kind,
                             container_count, merchant, sealed_on, origin_country,
                             status, sublot_of, notes, booked_in_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict (reference) do update set
                species_name = excluded.species_name,
                declared_weight_kg = excluded.declared_weight_kg,
                container_kind = excluded.container_kind,
                container_count = excluded.container_count,
                merchant = excluded.merchant,
                sealed_on = excluded.sealed_on,
                origin_country = excluded.origin_country,
                status = excluded.status,
                sublot_of = excluded.sublot_of,
                notes = excluded.notes
            """,
            (
                str(lot.reference),
                lot.species_name,
                to_text(lot.declared_weight_kg),
                lot.container_kind.value,
                lot.container_count,
                lot.merchant,
                to_iso(lot.sealed_on),
                lot.origin_country,
                lot.status.value,
                str(lot.sublot_of) if lot.sublot_of else None,
                lot.notes,
                to_iso(booked_in_on),
            ),
        )
        return lot

    def find(self, reference: LotReference | str) -> SeedLot | None:
        row = self._connection.execute(
            "select * from lot where reference = ?", (str(reference),)
        ).fetchone()
        return None if row is None else self._to_lot(row)

    def require(self, reference: LotReference | str) -> SeedLot:
        lot = self.find(reference)
        if lot is None:
            raise NotFound("lot", str(reference))
        return lot

    def open_lots(self) -> tuple[SeedLot, ...]:
        """Everything not yet closed, oldest first, which is the work queue."""
        rows = self._connection.execute(
            """
            select * from lot
            where status <> ?
            order by booked_in_at asc, reference asc
            """,
            (LotStatus.CLOSED.value,),
        ).fetchall()
        return tuple(self._to_lot(row) for row in rows)

    def for_species(self, species_name: str) -> tuple[SeedLot, ...]:
        rows = self._connection.execute(
            "select * from lot where species_name = ? order by reference asc",
            (species_name,),
        ).fetchall()
        return tuple(self._to_lot(row) for row in rows)

    def sublots_of(self, reference: LotReference | str) -> tuple[SeedLot, ...]:
        rows = self._connection.execute(
            "select * from lot where sublot_of = ? order by reference asc",
            (str(reference),),
        ).fetchall()
        return tuple(self._to_lot(row) for row in rows)

    def count(self) -> int:
        return int(self._connection.execute("select count(*) from lot").fetchone()[0])

    @staticmethod
    def _to_lot(row: sqlite3.Row) -> SeedLot:
        parent = row["sublot_of"]
        return SeedLot(
            reference=LotReference.parse(row["reference"]),
            species_name=row["species_name"],
            declared_weight_kg=to_decimal(row["declared_weight_kg"]),
            container_kind=to_enum(ContainerKind, row["container_kind"]),
            container_count=row["container_count"],
            merchant=row["merchant"],
            sealed_on=to_date(row["sealed_on"]),
            origin_country=row["origin_country"],
            status=to_enum(LotStatus, row["status"]),
            notes=row["notes"],
            sublot_of=LotReference.parse(parent) if parent else None,
        )
