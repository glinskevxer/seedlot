"""Reading and writing moisture and thousand seed weight.

Both are append only for the same reason the others are: a determination that
was made is part of what happened to the sample, and the duplicate rules only
mean something if both of the duplicates are still there to compare.

Moisture rows carry which stage they are. A predried sample produces three
rows, two stages and the combination, and reading only the last one would
report the second stage as if it were the whole moisture content, which on a
wet sample is out by five points or more.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from enum import Enum

from arc.moisture.determination import MoistureResult, Weighing
from arc.storage.codec import to_date, to_decimal, to_iso, to_optional_decimal, to_text
from arc.weight.thousand_seed import ThousandSeedWeight

__all__ = ["MoistureStage", "StoredMoisture", "MoistureRepository", "SeedWeightRepository"]


class MoistureStage(Enum):
    """Which part of a determination a row is.

    A sample dry enough to go straight in produces one row. A wet one produces
    a predry, a second stage, and the combination of the two.
    """

    SINGLE = "single"
    PREDRY = "predry"
    SECOND = "second"

    @property
    def is_part_of_a_pair(self) -> bool:
        return self is not MoistureStage.SINGLE


class StoredMoisture:
    """One moisture row as it came back."""

    def __init__(
        self,
        row_id: int,
        lot_reference: str,
        weighing: Weighing,
        result: MoistureResult,
        stage: MoistureStage,
        combined_percent: Decimal | None,
        analyst: str,
        determined_on: date,
    ) -> None:
        self.row_id = row_id
        self.lot_reference = lot_reference
        self.weighing = weighing
        self.result = result
        self.stage = stage
        self.combined_percent = combined_percent
        self.analyst = analyst
        self.determined_on = determined_on

    @property
    def reported_percent(self) -> Decimal:
        """What this row means as a moisture content.

        The combination if there is one, otherwise the row's own figure. A
        second stage on its own is not a moisture content and must never be
        read as one.
        """
        return self.combined_percent if self.combined_percent is not None else self.result.percent


class MoistureRepository:
    """Moisture determinations, one row per weighing."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        lot_reference: str,
        weighing: Weighing,
        result: MoistureResult,
        *,
        analyst: str,
        determined_on: date,
        stage: MoistureStage = MoistureStage.SINGLE,
        combined_percent: Decimal | None = None,
    ) -> int:
        cursor = self._connection.execute(
            """
            insert into moisture_determination
                (lot_reference, container_g, with_sample_g, after_drying_g,
                 percent, stage, combined_percent, analyst, determined_on)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot_reference,
                to_text(weighing.container_g),
                to_text(weighing.with_sample_g),
                to_text(weighing.after_drying_g),
                to_text(result.percent),
                stage.value,
                None if combined_percent is None else to_text(combined_percent),
                analyst,
                to_iso(determined_on),
            ),
        )
        return int(cursor.lastrowid or 0)

    def for_lot(self, lot_reference: str) -> tuple[StoredMoisture, ...]:
        rows = self._connection.execute(
            "select * from moisture_determination where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_stored(row) for row in rows)

    def reportable_for_lot(self, lot_reference: str) -> Decimal | None:
        """The moisture content that would go on a certificate, or nothing.

        A second stage row is skipped: it is arithmetic on the way to the
        combination, not a result in its own right.
        """
        rows = [
            stored
            for stored in self.for_lot(lot_reference)
            if stored.stage is not MoistureStage.SECOND or stored.combined_percent is not None
        ]
        return rows[-1].reported_percent if rows else None

    @staticmethod
    def _to_stored(row: sqlite3.Row) -> StoredMoisture:
        weighing = Weighing(
            container_g=to_decimal(row["container_g"]),
            with_sample_g=to_decimal(row["with_sample_g"]),
            after_drying_g=to_decimal(row["after_drying_g"]),
        )
        percent = to_decimal(row["percent"])
        return StoredMoisture(
            row_id=row["id"],
            lot_reference=row["lot_reference"],
            weighing=weighing,
            result=MoistureResult(
                percent=percent,
                wet_sample_g=weighing.wet_sample_g,
                water_lost_g=weighing.water_lost_g,
            ),
            stage=MoistureStage(row["stage"]),
            combined_percent=to_optional_decimal(row["combined_percent"]),
            analyst=row["analyst"],
            determined_on=to_date(row["determined_on"]),
        )


class SeedWeightRepository:
    """Thousand seed weight determinations and their eight replicates."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        lot_reference: str,
        determination: ThousandSeedWeight,
        *,
        analyst: str,
        determined_on: date,
    ) -> int:
        """Writes the determination and its replicates as one unit."""
        self._connection.execute("begin")
        try:
            cursor = self._connection.execute(
                """
                insert into seed_weight
                    (lot_reference, mean_g, deviation_g, variation, limit_applied,
                     grams_per_thousand, analyst, determined_on)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lot_reference,
                    to_text(determination.mean_g),
                    to_text(determination.standard_deviation_g),
                    to_text(determination.coefficient_of_variation),
                    to_text(determination.limit),
                    to_text(determination.grams_per_thousand),
                    analyst,
                    to_iso(determined_on),
                ),
            )
            weight_id = int(cursor.lastrowid or 0)

            for position, weight in enumerate(determination.replicate_weights_g, start=1):
                self._connection.execute(
                    """
                    insert into seed_weight_replicate (seed_weight_id, position, weight_g)
                    values (?, ?, ?)
                    """,
                    (weight_id, position, to_text(weight)),
                )
            self._connection.execute("commit")
        except Exception:
            self._connection.execute("rollback")
            raise

        return weight_id

    def for_lot(self, lot_reference: str) -> tuple[ThousandSeedWeight, ...]:
        rows = self._connection.execute(
            "select * from seed_weight where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_determination(row) for row in rows)

    def latest_for_lot(self, lot_reference: str) -> ThousandSeedWeight | None:
        found = self.for_lot(lot_reference)
        return found[-1] if found else None

    def _to_determination(self, row: sqlite3.Row) -> ThousandSeedWeight:
        replicates = self._connection.execute(
            "select weight_g from seed_weight_replicate where seed_weight_id = ? order by position",
            (row["id"],),
        ).fetchall()

        return ThousandSeedWeight(
            replicate_weights_g=tuple(to_decimal(item["weight_g"]) for item in replicates),
            mean_g=to_decimal(row["mean_g"]),
            standard_deviation_g=to_decimal(row["deviation_g"]),
            coefficient_of_variation=to_decimal(row["variation"]),
            limit=to_decimal(row["limit_applied"]),
        )
