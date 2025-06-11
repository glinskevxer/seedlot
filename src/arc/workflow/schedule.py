"""When a job will be finished, which is the question merchants ask.

Not the same question as what is outstanding. A merchant on the phone wants a
date, and the date is decided almost entirely by the germination, because that
is the only determination that takes weeks rather than an afternoon. Cocksfoot
prechilled for five days and counted on day twenty one is a month; wheat is
eight days.

The prediction is deliberately pessimistic in one direction. Where the station
does not know when a test was set down, it assumes the test starts today rather
than that it started when the lot arrived, because telling a merchant a date
that has already passed is worse than telling them a later one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from arc.germination.model import GerminationTest
from arc.lots.model import LotStatus, SeedLot
from arc.species.model import Species

__all__ = ["Expected", "expected_finish", "overdue_on"]

#: What the bench work either side of the germination takes. Purity is an
#: afternoon, moisture is a day, and the certificate is typed the same week.
BENCH_DAYS = 3


@dataclass(frozen=True)
class Expected:
    """When a lot should be done, and what the answer rests on."""

    lot_reference: str
    finish_on: date
    germination_finishes_on: date | None
    reason: str

    def days_from(self, day: date) -> int:
        return (self.finish_on - day).days

    def is_overdue_on(self, day: date) -> bool:
        return day > self.finish_on

    def describe(self, on: date) -> str:
        days = self.days_from(on)
        if days < 0:
            return f"{self.lot_reference} was due {self.finish_on}, {-days} days ago"
        return f"{self.lot_reference} due {self.finish_on} ({self.reason})"


def expected_finish(
    lot: SeedLot,
    species: Species,
    tests: tuple[GerminationTest, ...],
    *,
    on: date,
) -> Expected:
    """When this lot's work should be finished.

    The rules stack rather than branch. A lot that is already reported is
    finished today whatever else is true; a germination that has been set down
    decides the date; and with nothing set down the clock starts now.
    """
    reference = str(lot.reference)

    if lot.status in (LotStatus.REPORTED, LotStatus.CLOSED):
        return Expected(
            lot_reference=reference,
            finish_on=on,
            germination_finishes_on=None,
            reason="already reported",
        )

    duration = species.germination.duration_days

    if tests:
        latest = tests[-1]
        germination_finishes = latest.set_down_on + timedelta(days=duration)
        reason = f"germination set down {latest.set_down_on}, {duration} days"
    else:
        germination_finishes = on + timedelta(days=duration)
        reason = f"germination not set down yet, {duration} days once it is"

    return Expected(
        lot_reference=reference,
        finish_on=germination_finishes + timedelta(days=BENCH_DAYS),
        germination_finishes_on=germination_finishes,
        reason=reason,
    )


def overdue_on(expected: tuple[Expected, ...], day: date) -> tuple[Expected, ...]:
    """Everything that should have been finished by that day, latest first."""
    late = [item for item in expected if item.is_overdue_on(day)]
    return tuple(sorted(late, key=lambda item: item.finish_on))
