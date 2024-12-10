"""Reading and writing the determinations made against a lot.

Everything here is append only. A purity analysis that turns out wrong is not
edited: a second one is recorded and the two are compared, because the whole
apparatus of duplicate tolerances exists to answer the question "do these two
analyses agree" and an edited row destroys the question.

The percentages are stored alongside the weights they came from. Recomputing
them on read would look tidier and would mean a later change to the rounding
rule silently rewrote results that were already certified.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from arc.germination.model import GerminationTest, Replicate, Treatment
from arc.purity.analysis import PurityAnalysis, PurityResult
from arc.storage.codec import (
    from_bool,
    to_bool,
    to_date,
    to_decimal,
    to_iso,
    to_optional_decimal,
    to_text,
)

__all__ = ["PurityRepository", "GerminationRepository", "StoredPurity"]


class StoredPurity:
    """One purity analysis as it came back out of the database."""

    def __init__(
        self,
        row_id: int,
        lot_reference: str,
        analysis: PurityAnalysis,
        analysed_on: date,
        is_duplicate: bool,
        pure_seed_percent: Decimal | None,
        other_seed_percent: Decimal | None,
        inert_percent: Decimal | None,
    ) -> None:
        self.row_id = row_id
        self.lot_reference = lot_reference
        self.analysis = analysis
        self.analysed_on = analysed_on
        self.is_duplicate = is_duplicate
        self.pure_seed_percent = pure_seed_percent
        self.other_seed_percent = other_seed_percent
        self.inert_percent = inert_percent

    @property
    def was_computed(self) -> bool:
        """False for an analysis that was recorded but never worked out."""
        return self.pure_seed_percent is not None


class PurityRepository:
    """Purity analyses, one row per time the sample went on the board."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        lot_reference: str,
        analysis: PurityAnalysis,
        result: PurityResult | None,
        *,
        analysed_on: date,
        is_duplicate: bool = False,
    ) -> int:
        """Writes one analysis and returns the row it was given."""
        cursor = self._connection.execute(
            """
            insert into purity_analysis
                (lot_reference, working_sample_g, pure_seed_g, other_seed_g,
                 inert_matter_g, pure_seed_percent, other_seed_percent,
                 inert_percent, analyst, analysed_on, is_duplicate)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot_reference,
                to_text(analysis.working_sample_g),
                to_text(analysis.pure_seed_g),
                to_text(analysis.other_seed_g),
                to_text(analysis.inert_matter_g),
                None if result is None else to_text(result.pure_seed.value),
                None if result is None else to_text(result.other_seed.value),
                None if result is None else to_text(result.inert_matter.value),
                analysis.analyst,
                to_iso(analysed_on),
                from_bool(is_duplicate),
            ),
        )
        return int(cursor.lastrowid or 0)

    def for_lot(self, lot_reference: str) -> tuple[StoredPurity, ...]:
        """Every analysis of that lot, in the order they were made."""
        rows = self._connection.execute(
            "select * from purity_analysis where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_stored(row) for row in rows)

    def latest_for_lot(self, lot_reference: str) -> StoredPurity | None:
        found = self.for_lot(lot_reference)
        return found[-1] if found else None

    @staticmethod
    def _to_stored(row: sqlite3.Row) -> StoredPurity:
        return StoredPurity(
            row_id=row["id"],
            lot_reference=row["lot_reference"],
            analysis=PurityAnalysis(
                working_sample_g=to_decimal(row["working_sample_g"]),
                pure_seed_g=to_decimal(row["pure_seed_g"]),
                other_seed_g=to_decimal(row["other_seed_g"]),
                inert_matter_g=to_decimal(row["inert_matter_g"]),
                analyst=row["analyst"],
            ),
            analysed_on=to_date(row["analysed_on"]),
            is_duplicate=to_bool(row["is_duplicate"]),
            pure_seed_percent=to_optional_decimal(row["pure_seed_percent"]),
            other_seed_percent=to_optional_decimal(row["other_seed_percent"]),
            inert_percent=to_optional_decimal(row["inert_percent"]),
        )


class GerminationRepository:
    """Germination tests and the trays that make them up."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(self, test: GerminationTest) -> int:
        """Writes a test and its replicates as one unit.

        A test without its trays is worse than no test at all: it carries a
        mean nobody can check. So both go in inside one transaction.
        """
        self._connection.execute("begin")
        try:
            cursor = self._connection.execute(
                """
                insert into germination_test
                    (lot_reference, seeds_per_replicate, replicate_count,
                     set_down_on, final_count_on, analyst, is_retest,
                     treatment, mean_normal, replicate_range)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test.lot_reference,
                    test.seeds_per_replicate,
                    len(test.replicates),
                    to_iso(test.set_down_on),
                    to_iso(test.final_count_on),
                    test.analyst,
                    from_bool(test.is_retest),
                    test.treatment.value,
                    test.mean_normal,
                    to_text(test.replicate_range),
                ),
            )
            test_id = int(cursor.lastrowid or 0)

            for position, replicate in enumerate(test.replicates, start=1):
                self._connection.execute(
                    """
                    insert into germination_replicate
                        (test_id, position, normal, abnormal, hard, fresh, dead)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        test_id,
                        position,
                        replicate.normal,
                        replicate.abnormal,
                        replicate.hard,
                        replicate.fresh,
                        replicate.dead,
                    ),
                )
            self._connection.execute("commit")
        except Exception:
            self._connection.execute("rollback")
            raise

        return test_id

    def for_lot(self, lot_reference: str) -> tuple[GerminationTest, ...]:
        rows = self._connection.execute(
            "select * from germination_test where lot_reference = ? order by id asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_test(row) for row in rows)

    def _to_test(self, row: sqlite3.Row) -> GerminationTest:
        replicate_rows = self._connection.execute(
            """
            select * from germination_replicate
            where test_id = ? order by position asc
            """,
            (row["id"],),
        ).fetchall()

        return GerminationTest(
            lot_reference=row["lot_reference"],
            species_name="",
            replicates=tuple(
                Replicate(
                    normal=item["normal"],
                    abnormal=item["abnormal"],
                    hard=item["hard"],
                    fresh=item["fresh"],
                    dead=item["dead"],
                )
                for item in replicate_rows
            ),
            seeds_per_replicate=row["seeds_per_replicate"],
            set_down_on=to_date(row["set_down_on"]),
            final_count_on=to_date(row["final_count_on"]),
            analyst=row["analyst"],
            is_retest=to_bool(row["is_retest"]),
            treatment=Treatment(row["treatment"]),
        )
