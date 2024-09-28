"""Reading and writing searches for other species.

Two tables rather than one, because a search finds a variable number of species
and the alternative is a text column holding a list, which cannot be queried
and goes stale the first time somebody edits it by hand.

The species that were looked for do live in a text column, and that is
deliberate. They are what the customer asked for, they are never joined
against, and a fourth table to hold three words would be a table nobody reads.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.storage.codec import to_date, to_decimal, to_iso, to_text

__all__ = ["StoredSearch", "OtherSeedRepository"]

#: What separates the sought species inside the one text column. A semicolon
#: rather than a comma because botanical names do not contain semicolons and
#: some common names do contain commas.
SEPARATOR = ";"


class StoredSearch:
    """One search as it came back, with the row id and the date it was done."""

    def __init__(
        self,
        row_id: int,
        lot_reference: str,
        search: OtherSeedSearch,
        searched_on: date,
    ) -> None:
        self.row_id = row_id
        self.lot_reference = lot_reference
        self.search = search
        self.searched_on = searched_on

    @property
    def kind(self) -> SearchKind:
        return self.search.kind

    def __repr__(self) -> str:
        return f"<StoredSearch {self.row_id} {self.lot_reference} {self.search.describe()}>"


class OtherSeedRepository:
    """Searches, append only like every other determination."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        lot_reference: str,
        search: OtherSeedSearch,
        *,
        searched_on: date,
    ) -> int:
        """Writes the search and its findings as one unit.

        In a transaction because a search whose findings did not make it is
        worse than no search at all: it reads as a nil return, which is the one
        result a buyer acts on.
        """
        self._connection.execute("begin")
        try:
            cursor = self._connection.execute(
                """
                insert into other_seed_search
                    (lot_reference, species_name, kind, weight_examined_g,
                     sought, analyst, searched_on)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lot_reference,
                    search.species_name,
                    search.kind.value,
                    to_text(search.weight_examined_g),
                    SEPARATOR.join(search.sought),
                    search.analyst,
                    to_iso(searched_on),
                ),
            )
            search_id = int(cursor.lastrowid or 0)

            for finding in search.findings:
                self._connection.execute(
                    """
                    insert into other_seed_finding (search_id, species_name, count)
                    values (?, ?, ?)
                    """,
                    (search_id, finding.species_name, finding.count),
                )
            self._connection.execute("commit")
        except Exception:
            self._connection.execute("rollback")
            raise

        return search_id

    def for_lot(self, lot_reference: str) -> tuple[StoredSearch, ...]:
        rows = self._connection.execute(
            "select * from other_seed_search where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_search(row) for row in rows)

    def latest_for_lot(self, lot_reference: str) -> StoredSearch | None:
        found = self.for_lot(lot_reference)
        return found[-1] if found else None

    def counts_of(self, lot_reference: str, species_name: str) -> tuple[int, ...]:
        """Every count of one species against this lot, oldest first.

        Two of these are what the tolerance between counts is applied to, and
        keeping them in the order they were done means the pair being compared
        is the pair that was actually done second and first.
        """
        wanted = species_name.strip().lower()
        return tuple(
            stored.search.count_of(species_name)
            for stored in self.for_lot(lot_reference)
            if stored.search.was_sought(wanted)
        )

    def _to_search(self, row: sqlite3.Row) -> StoredSearch:
        findings = self._connection.execute(
            "select species_name, count from other_seed_finding "
            "where search_id = ? order by id asc",
            (row["id"],),
        ).fetchall()

        sought = tuple(name for name in str(row["sought"]).split(SEPARATOR) if name.strip())

        return StoredSearch(
            row_id=int(row["id"]),
            lot_reference=row["lot_reference"],
            search=OtherSeedSearch(
                species_name=row["species_name"],
                kind=SearchKind(row["kind"]),
                weight_examined_g=to_decimal(row["weight_examined_g"]),
                findings=tuple(
                    Finding(item["species_name"], int(item["count"])) for item in findings
                ),
                sought=sought,
                analyst=row["analyst"],
            ),
            searched_on=to_date(row["searched_on"]),
        )
