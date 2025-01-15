"""Reading and writing what is left in the sample store.

This is the one table in the database that is updated in place rather than
appended to, because the remaining weight is a fact about now and not a record
of an event. The events are in the draw table beside it, and the remaining
weight has to be reconstructible from them, so every draw writes both or
neither.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from arc.certificates.model import CertificateKind
from arc.errors import NotFound
from arc.retention.model import Determination, DisposalReason, RetainedSample
from arc.storage.codec import to_date, to_decimal, to_iso, to_optional_date, to_text

__all__ = ["Draw", "RetentionRepository"]


@dataclass(frozen=True)
class Draw:
    """One withdrawal from the store, as it happened."""

    lot_reference: str
    determination: Determination
    weight_g: Decimal
    drawn_on: date
    analyst: str


class RetentionRepository:
    """The sample store: what is held, what has come out, what has gone."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def place(self, sample: RetainedSample) -> None:
        """Puts a sample into the store, or replaces the one already there.

        Replacing rather than refusing is deliberate. A lot certified twice
        gets its retention period reset to the later certificate, because that
        is the claim the sample now has to back.
        """
        self._connection.execute(
            """
            insert into retained_sample
                (lot_reference, species_name, remaining_g, held_from,
                 certificate_kind, disposed_on, disposal_reason)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict (lot_reference) do update set
                species_name = excluded.species_name,
                remaining_g = excluded.remaining_g,
                held_from = excluded.held_from,
                certificate_kind = excluded.certificate_kind,
                disposed_on = excluded.disposed_on,
                disposal_reason = excluded.disposal_reason
            """,
            (
                sample.lot_reference,
                sample.species_name,
                to_text(sample.remaining_g),
                to_iso(sample.held_from),
                None if sample.certificate_kind is None else sample.certificate_kind.value,
                None if sample.disposed_on is None else to_iso(sample.disposed_on),
                None if sample.disposal_reason is None else sample.disposal_reason.value,
            ),
        )

    def find(self, lot_reference: str) -> RetainedSample | None:
        row = self._connection.execute(
            "select * from retained_sample where lot_reference = ?",
            (lot_reference,),
        ).fetchone()
        return None if row is None else self._to_sample(row)

    def require(self, lot_reference: str) -> RetainedSample:
        found = self.find(lot_reference)
        if found is None:
            raise NotFound("retained sample", lot_reference)
        return found

    def draw(
        self,
        lot_reference: str,
        determination: Determination,
        weight_g: Decimal,
        *,
        on: date,
        analyst: str,
    ) -> RetainedSample:
        """Takes seed out for a repeat test and says what is left.

        The subtraction goes through the sample rather than through SQL so that
        drawing more than is there is refused by the same code that refuses it
        everywhere else, rather than by a check somebody has to remember to
        write beside every update.
        """
        sample = self.require(lot_reference)
        left = sample.draw(weight_g)

        self._connection.execute("begin")
        try:
            self._connection.execute(
                "update retained_sample set remaining_g = ? where lot_reference = ?",
                (to_text(left.remaining_g), lot_reference),
            )
            self._connection.execute(
                """
                insert into retained_draw
                    (lot_reference, determination, weight_g, drawn_on, analyst)
                values (?, ?, ?, ?, ?)
                """,
                (
                    lot_reference,
                    determination.value,
                    to_text(weight_g),
                    to_iso(on),
                    analyst,
                ),
            )
            self._connection.execute("commit")
        except Exception:
            self._connection.execute("rollback")
            raise

        return left

    def dispose(
        self,
        lot_reference: str,
        *,
        on: date,
        reason: DisposalReason,
    ) -> RetainedSample:
        """Marks a sample as gone. The row stays; the seed does not."""
        sample = self.require(lot_reference)
        if not sample.is_held:
            raise ValueError(f"{lot_reference} was already disposed of {sample.disposed_on}")

        self._connection.execute(
            """
            update retained_sample
            set disposed_on = ?, disposal_reason = ?
            where lot_reference = ?
            """,
            (to_iso(on), reason.value, lot_reference),
        )
        return self.require(lot_reference)

    def held(self) -> tuple[RetainedSample, ...]:
        """Everything still in the store, oldest first."""
        rows = self._connection.execute(
            "select * from retained_sample where disposed_on is null "
            "order by held_from asc, lot_reference asc"
        ).fetchall()
        return tuple(self._to_sample(row) for row in rows)

    def due_for_disposal(self, on: date) -> tuple[RetainedSample, ...]:
        """Everything whose period has run out by that day.

        Worked out in Python rather than in SQL because the period depends on
        which certificate was issued, and putting that table into a case
        expression would give the rule two homes.
        """
        return tuple(sample for sample in self.held() if sample.is_due_for_disposal_on(on))

    def draws_for(self, lot_reference: str) -> tuple[Draw, ...]:
        rows = self._connection.execute(
            "select * from retained_draw where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(
            Draw(
                lot_reference=row["lot_reference"],
                determination=Determination(row["determination"]),
                weight_g=to_decimal(row["weight_g"]),
                drawn_on=to_date(row["drawn_on"]),
                analyst=row["analyst"],
            )
            for row in rows
        )

    def _to_sample(self, row: sqlite3.Row) -> RetainedSample:
        kind = row["certificate_kind"]
        reason = row["disposal_reason"]

        return RetainedSample(
            lot_reference=row["lot_reference"],
            species_name=row["species_name"],
            remaining_g=to_decimal(row["remaining_g"]),
            held_from=to_date(row["held_from"]),
            certificate_kind=None if kind is None else CertificateKind(kind),
            disposed_on=to_optional_date(row["disposed_on"]),
            disposal_reason=None if reason is None else DisposalReason(reason),
        )
