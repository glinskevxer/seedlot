"""What to do with a germination test once it has been counted.

Three tables meet here and the order they are consulted in is the rule.

First the replicate range decides whether the test stands at all. A test whose
trays spread too far is not a low result or a high one, it is not a result, and
the only thing to do with it is set the whole thing down again.

Then, if there is a second test, the two are held up against each other. Two
tests of the same sample are allowed to differ by less than four trays of one
test are, because between them they have eight hundred seeds. If they agree,
the sample germinates at the mean of the two and that is what the certificate
says. If they do not, neither test describes the sample and the station goes
back to the submitted sample for a fresh working sample.

The order matters because a second test that is itself in range ends the
question. There is no point comparing a good test to a bad one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from arc.germination.model import GerminationTest
from arc.germination.tolerance import check_range

__all__ = [
    "Verdict",
    "BETWEEN_TEST_TOLERANCES",
    "between_tests_tolerance",
    "GerminationOutcome",
    "decide",
]


class Verdict(Enum):
    """What the station does next."""

    REPORT = "report"
    REPEAT = "repeat the test"
    REPORT_MEAN_OF_BOTH = "report the mean of both tests"
    DRAW_A_FRESH_SAMPLE = "draw a fresh working sample"

    @property
    def is_final(self) -> bool:
        return self in (Verdict.REPORT, Verdict.REPORT_MEAN_OF_BOTH)


#: Tolerance between two complete tests of the same sample, folded around
#: fifty like the others. Read top down on the folded mean.
BETWEEN_TEST_TOLERANCES: tuple[tuple[int, int], ...] = (
    (45, 8),
    (24, 7),
    (16, 6),
    (10, 5),
    (6, 4),
    (3, 3),
    (1, 2),
    (0, 2),
)


def between_tests_tolerance(mean_percent: int) -> int:
    """How far two whole tests of one sample may differ.

    Tighter than the range allowed inside a single test, because two tests
    between them have twice the seeds and half the excuse.
    """
    if not 0 <= mean_percent <= 100:
        raise ValueError(f"a germination percentage runs from 0 to 100, not {mean_percent}")
    folded = min(mean_percent, 100 - mean_percent)
    for floor, tolerance in BETWEEN_TEST_TOLERANCES:
        if folded >= floor:
            return tolerance
    raise AssertionError("the last band starts at zero and must have matched")


@dataclass(frozen=True)
class GerminationOutcome:
    """The decision, and everything it was made from."""

    verdict: Verdict
    reported_percent: int | None
    first_percent: int
    second_percent: int | None
    reason: str

    @property
    def needs_more_work(self) -> bool:
        return not self.verdict.is_final


def decide(first: GerminationTest, second: GerminationTest | None = None) -> GerminationOutcome:
    """What to do with one test, or with a test and its repeat."""
    first_check = check_range(first.mean_normal, first.replicate_range)

    if first_check.within_tolerance:
        return GerminationOutcome(
            verdict=Verdict.REPORT,
            reported_percent=first.mean_normal,
            first_percent=first.mean_normal,
            second_percent=second.mean_normal if second else None,
            reason=first_check.explain(),
        )

    if second is None:
        return GerminationOutcome(
            verdict=Verdict.REPEAT,
            reported_percent=None,
            first_percent=first.mean_normal,
            second_percent=None,
            reason=first_check.explain(),
        )

    second_check = check_range(second.mean_normal, second.replicate_range)
    if second_check.within_tolerance:
        return GerminationOutcome(
            verdict=Verdict.REPORT,
            reported_percent=second.mean_normal,
            first_percent=first.mean_normal,
            second_percent=second.mean_normal,
            reason=(
                "the first test spread too far and the repeat did not, "
                f"so the repeat stands: {second_check.explain()}"
            ),
        )

    mean_of_both = _mean_of(first.mean_normal, second.mean_normal)
    allowed = between_tests_tolerance(mean_of_both)
    apart = abs(first.mean_normal - second.mean_normal)

    if apart <= allowed:
        return GerminationOutcome(
            verdict=Verdict.REPORT_MEAN_OF_BOTH,
            reported_percent=mean_of_both,
            first_percent=first.mean_normal,
            second_percent=second.mean_normal,
            reason=(
                f"both tests spread too far but they agree with each other, "
                f"{apart} apart against the {allowed} allowed at {mean_of_both} percent"
            ),
        )

    return GerminationOutcome(
        verdict=Verdict.DRAW_A_FRESH_SAMPLE,
        reported_percent=None,
        first_percent=first.mean_normal,
        second_percent=second.mean_normal,
        reason=(
            f"both tests spread too far and they do not agree either, "
            f"{apart} apart against the {allowed} allowed at {mean_of_both} percent"
        ),
    )


def _mean_of(first: int, second: int) -> int:
    return int((Decimal(first + second) / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
