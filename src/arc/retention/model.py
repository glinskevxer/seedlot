"""The retained sample, and how long it has to be kept.

The period runs from the certificate rather than from the day the sample
arrived, because it exists to cover the claim, and the claim starts when the
certificate does. A sample tested in March and certified in June is held from
June.

What is left of the sample matters as much as how long it has been held. Every
determination has a working sample size, testing consumes it, and a retained
sample that has been drawn on twice may be too small to repeat the very test it
is being kept for. That is not an error anybody notices until they need it, so
it is worked out here and refused there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from arc.certificates.model import CertificateKind

__all__ = [
    "Determination",
    "DisposalReason",
    "RETENTION_PERIODS",
    "UNCERTIFIED_RETENTION",
    "RetainedSample",
    "retention_period",
]


class Determination(Enum):
    """A test that might be asked for again, and what it costs in seed."""

    PURITY = "purity"
    GERMINATION = "germination"
    OTHER_SEED = "other seed by number"
    MOISTURE = "moisture"
    THOUSAND_SEED_WEIGHT = "thousand seed weight"

    @property
    def label(self) -> str:
        return self.value


class DisposalReason(Enum):
    """Why a retained sample is no longer held."""

    PERIOD_EXPIRED = "retention period expired"
    RETURNED_TO_MERCHANT = "returned to the merchant"
    CONSUMED_BY_TESTING = "used up in testing"
    SPOILED = "spoiled in store"

    @property
    def is_ordinary(self) -> bool:
        """Whether this is the disposal the calendar was always going to make."""
        return self is DisposalReason.PERIOD_EXPIRED


#: How long each kind of certificate has to be backed by a sample. The orange
#: one crosses a border and gets the longest, because a dispute has to travel
#: back before anybody can raise it.
RETENTION_PERIODS: dict[CertificateKind, timedelta] = {
    CertificateKind.ORANGE_INTERNATIONAL: timedelta(days=365),
    CertificateKind.BLUE_INTERNATIONAL: timedelta(days=365),
    CertificateKind.GREEN_ANALYSIS: timedelta(days=182),
}

#: A sample that was never certified is still held, for long enough that the
#: merchant who sent it can ask what happened to it.
UNCERTIFIED_RETENTION = timedelta(days=90)


def retention_period(kind: CertificateKind | None) -> timedelta:
    """How long a sample is held, given what was issued off it."""
    if kind is None:
        return UNCERTIFIED_RETENTION
    return RETENTION_PERIODS[kind]


@dataclass(frozen=True)
class RetainedSample:
    """What is left of one submitted sample, and since when."""

    lot_reference: str
    species_name: str
    remaining_g: Decimal
    held_from: date
    certificate_kind: CertificateKind | None = None
    disposed_on: date | None = None
    disposal_reason: DisposalReason | None = None

    def __post_init__(self) -> None:
        if self.remaining_g < 0:
            raise ValueError("a sample cannot have less than nothing left of it")
        if self.disposed_on is not None and self.disposal_reason is None:
            raise ValueError("a disposal has to say why")
        if self.disposed_on is not None and self.disposed_on < self.held_from:
            raise ValueError("a sample cannot be disposed of before it was held")

    @property
    def is_held(self) -> bool:
        return self.disposed_on is None

    @property
    def hold_until(self) -> date:
        """The last day the station has to be able to produce this sample."""
        return self.held_from + retention_period(self.certificate_kind)

    def is_due_for_disposal_on(self, day: date) -> bool:
        """Whether the period has run out by that day."""
        return self.is_held and day > self.hold_until

    def days_left_on(self, day: date) -> int:
        """How many days are left to run. Negative once the period is past."""
        return (self.hold_until - day).days

    def draw(self, weight_g: Decimal) -> RetainedSample:
        """Takes seed out of the sample, leaving a new one behind.

        Returns a fresh sample rather than changing this one, because the
        weight before the draw is what an audit reconstructs the working
        sample from.
        """
        if weight_g <= 0:
            raise ValueError("drawing nothing out of a sample is not a draw")
        if weight_g > self.remaining_g:
            raise ValueError(
                f"{weight_g} g cannot come out of a sample holding {self.remaining_g} g"
            )

        return RetainedSample(
            lot_reference=self.lot_reference,
            species_name=self.species_name,
            remaining_g=self.remaining_g - weight_g,
            held_from=self.held_from,
            certificate_kind=self.certificate_kind,
        )

    def describe(self, on: date) -> str:
        """One line for the store list."""
        if not self.is_held:
            reason = self.disposal_reason.value if self.disposal_reason else "unstated"
            return f"{self.lot_reference} disposed {self.disposed_on}, {reason}"

        days = self.days_left_on(on)
        if days < 0:
            return f"{self.lot_reference} {self.remaining_g} g, {-days} days overdue"
        return f"{self.lot_reference} {self.remaining_g} g, {days} days left"
