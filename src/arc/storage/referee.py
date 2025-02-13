"""Comparisons against another laboratory, written down and kept.

A merchant who does not like a result sends the sample somewhere else. What
comes back is not a correction and it does not replace anything: it is a second
opinion, and the two are either close enough to both be right or they are not.
Either way the comparison is part of the lot's history, because the next
question anybody asks is what happened last time this merchant disputed a
result.

The verdict is stored rather than worked out on the way back. The allowance
tables move between editions of the handbook, and a comparison that was made
under the old table has to keep reading the way it read when it was made.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from arc.referee.between_labs import Referee, RefereeVerdict
from arc.retention.model import Determination
from arc.storage.codec import to_date, to_decimal, to_iso, to_text

__all__ = ["StoredComparison", "RefereeRepository"]

#: The two determinations a laboratory is asked to referee. Moisture and seed
#: weight are not disputed this way: they are repeated, not argued about.
REFEREEABLE = (Determination.PURITY, Determination.GERMINATION)


@dataclass(frozen=True)
class StoredComparison:
    """One comparison as it was made, with who asked for it."""

    row_id: int
    lot_reference: str
    certificate_number: str
    determination: Determination
    referee: Referee
    other_laboratory: str
    raised_by: str
    compared_on: date

    @property
    def stands(self) -> bool:
        """Whether our result survived the comparison."""
        return self.referee.verdict is RefereeVerdict.AGREE

    def describe(self) -> str:
        return (
            f"{self.compared_on} {self.determination.value} against "
            f"{self.other_laboratory}: {self.referee.explain()}"
        )


class RefereeRepository:
    """Referee comparisons, appended and never changed."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        lot_reference: str,
        certificate_number: str,
        determination: Determination,
        referee: Referee,
        *,
        other_laboratory: str,
        raised_by: str,
        on: date,
    ) -> int:
        """Writes one comparison down."""
        if determination not in REFEREEABLE:
            raise ValueError(f"{determination.value} is not refereed between laboratories")

        cursor = self._connection.execute(
            """
            insert into referee_comparison
                (lot_reference, certificate_number, determination, ours, theirs,
                 allowance, verdict, other_laboratory, raised_by, compared_on)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot_reference,
                certificate_number,
                determination.value,
                to_text(referee.ours),
                to_text(referee.theirs),
                to_text(referee.allowance),
                "agree" if referee.verdict is RefereeVerdict.AGREE else "refer",
                other_laboratory,
                raised_by,
                to_iso(on),
            ),
        )
        return int(cursor.lastrowid or 0)

    def for_lot(self, lot_reference: str) -> tuple[StoredComparison, ...]:
        rows = self._connection.execute(
            "select * from referee_comparison where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_comparison(row) for row in rows)

    def for_certificate(self, number: str) -> tuple[StoredComparison, ...]:
        rows = self._connection.execute(
            "select * from referee_comparison where certificate_number = ? " "order by id asc",
            (number,),
        ).fetchall()
        return tuple(self._to_comparison(row) for row in rows)

    def disputed(self) -> tuple[StoredComparison, ...]:
        """Every comparison that did not agree, newest first.

        The list somebody wants when a merchant is on the phone, and the list
        the accreditation body asks for at audit.
        """
        rows = self._connection.execute(
            "select * from referee_comparison where verdict = 'refer' "
            "order by compared_on desc, id desc"
        ).fetchall()
        return tuple(self._to_comparison(row) for row in rows)

    def _to_comparison(self, row: sqlite3.Row) -> StoredComparison:
        verdict = RefereeVerdict.AGREE if row["verdict"] == "agree" else RefereeVerdict.REFER

        return StoredComparison(
            row_id=int(row["id"]),
            lot_reference=row["lot_reference"],
            certificate_number=row["certificate_number"],
            determination=Determination(row["determination"]),
            referee=Referee(
                ours=to_decimal(row["ours"]),
                theirs=to_decimal(row["theirs"]),
                allowance=to_decimal(row["allowance"]),
                verdict=verdict,
            ),
            other_laboratory=row["other_laboratory"],
            raised_by=row["raised_by"],
            compared_on=to_date(row["compared_on"]),
        )
