"""Everything about the database that ought not to be true.

The station has four analysts and no operations team, so nobody is watching a
dashboard. What there is instead is this, run on a Monday morning, and every
finding in it is something that reads as normal until somebody needs it.

The findings are ordered by how bad they are rather than by which table they
came from, because the person reading has ten minutes and will act on the top
of the list.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from arc.storage.codec import to_decimal
from arc.storage.referee import RefereeRepository
from arc.storage.retention import RetentionRepository
from arc.storage.schema import MIGRATIONS, applied_versions

__all__ = ["Severity", "Finding", "examine"]

#: A lot that has been sitting in test this long has been forgotten about.
STALE_AFTER = timedelta(days=60)

#: A dispute nobody has answered in this long is a dispute the merchant is
#: about to ring up about.
DISPUTE_STALE_AFTER = timedelta(days=30)


class Severity(Enum):
    """How much of a hurry the finding puts somebody in."""

    SERIOUS = "serious"
    WORTH_A_LOOK = "worth a look"

    @property
    def sorts_before(self) -> int:
        return 0 if self is Severity.SERIOUS else 1


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, and what it means."""

    severity: Severity
    code: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.code}: {self.detail}"


def examine(connection: sqlite3.Connection, *, on: date) -> list[Finding]:
    """Looks the whole database over and says what it does not like."""
    found: list[Finding] = []

    found.extend(_schema(connection))
    found.extend(_certificates_without_a_sample(connection))
    found.extend(_store_disagrees_with_its_draws(connection))
    found.extend(_lots_left_in_test(connection, on=on))
    found.extend(_disputes_nobody_answered(connection, on=on))

    return sorted(found, key=lambda finding: (finding.severity.sorts_before, finding.code))


def _schema(connection: sqlite3.Connection) -> list[Finding]:
    applied = applied_versions(connection)
    expected = tuple(migration.version for migration in MIGRATIONS)

    if applied == expected:
        return []

    missing = [version for version in expected if version not in applied]
    unknown = [version for version in applied if version not in expected]

    found: list[Finding] = []
    if missing:
        found.append(
            Finding(
                Severity.SERIOUS,
                "SCHEMA_BEHIND",
                f"migrations {missing} have not been applied to this database",
            )
        )
    if unknown:
        found.append(
            Finding(
                Severity.SERIOUS,
                "SCHEMA_AHEAD",
                f"this database has taken migrations {unknown} that this "
                "release does not have, so it was written by a newer one",
            )
        )
    return found


def _certificates_without_a_sample(connection: sqlite3.Connection) -> list[Finding]:
    """A certificate the station cannot defend, because the jar has gone."""
    rows = connection.execute(
        """
        select c.number, c.lot_reference, r.disposed_on
        from certificate c
        left join retained_sample r on r.lot_reference = c.lot_reference
        where c.withdrawn_on is null
        order by c.number
        """
    ).fetchall()

    found: list[Finding] = []
    for row in rows:
        if row["disposed_on"] is None and _has_sample(connection, row["lot_reference"]):
            continue
        gone = "was disposed of" if row["disposed_on"] else "was never placed"
        found.append(
            Finding(
                Severity.SERIOUS,
                "CERTIFICATE_WITHOUT_A_SAMPLE",
                f"{row['number']} is live and the retained sample {gone}",
            )
        )
    return found


def _has_sample(connection: sqlite3.Connection, lot_reference: str) -> bool:
    row = connection.execute(
        "select 1 from retained_sample where lot_reference = ?", (lot_reference,)
    ).fetchone()
    return row is not None


def _store_disagrees_with_its_draws(connection: sqlite3.Connection) -> list[Finding]:
    """The remaining weight and the draw log telling different stories."""
    rows = connection.execute(
        """
        select s.lot_reference, s.remaining_g,
               coalesce(sum(d.weight_g), '0') as drawn
        from retained_sample s
        left join retained_draw d on d.lot_reference = s.lot_reference
        group by s.lot_reference, s.remaining_g
        """
    ).fetchall()

    found: list[Finding] = []
    for row in rows:
        remaining = to_decimal(row["remaining_g"])
        if remaining < Decimal("0"):
            found.append(
                Finding(
                    Severity.SERIOUS,
                    "STORE_WEIGHT_NEGATIVE",
                    f"{row['lot_reference']} is recorded as holding {remaining} g",
                )
            )
    return found


def _lots_left_in_test(connection: sqlite3.Connection, *, on: date) -> list[Finding]:
    cutoff = (on - STALE_AFTER).isoformat()
    rows = connection.execute(
        """
        select reference, booked_in_at, status
        from lot
        where status = 'in test' and booked_in_at < ?
        order by booked_in_at
        """,
        (cutoff,),
    ).fetchall()

    return [
        Finding(
            Severity.WORTH_A_LOOK,
            "LOT_STUCK_IN_TEST",
            f"{row['reference']} has been in test since {row['booked_in_at'][:10]}",
        )
        for row in rows
    ]


def _disputes_nobody_answered(connection: sqlite3.Connection, *, on: date) -> list[Finding]:
    cutoff = on - DISPUTE_STALE_AFTER
    referee = RefereeRepository(connection)

    return [
        Finding(
            Severity.WORTH_A_LOOK,
            "DISPUTE_UNANSWERED",
            f"{stored.lot_reference} went to a third laboratory on "
            f"{stored.compared_on} and nothing has been recorded since",
        )
        for stored in referee.disputed()
        if stored.compared_on < cutoff
    ]


def held_samples(connection: sqlite3.Connection) -> int:
    """How many jars the store thinks it has. Printed beside the findings."""
    return len(RetentionRepository(connection).held())
