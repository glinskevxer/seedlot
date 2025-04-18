"""What the station did, counted.

Once a year the accreditation body asks how much work went through and how it
came out, and once a quarter the person who runs the place wants to know
whether the germination cabinets are keeping up. Both questions are the same
few counts over the certificates that were issued.

Everything here counts certificates rather than tests. A lot tested three times
and certified once is one job, and counting the tests would make a bad month
look like a busy one.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from arc.certificates.model import Certificate, CertificateKind
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository

__all__ = [
    "MonthlyCount",
    "SpeciesSummary",
    "Turnaround",
    "by_month",
    "by_species",
    "turnaround",
]


@dataclass(frozen=True)
class MonthlyCount:
    """One month's work."""

    year: int
    month: int
    issued: int
    withdrawn: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def stood(self) -> int:
        """Certificates that were issued and not taken back."""
        return self.issued - self.withdrawn


@dataclass(frozen=True)
class SpeciesSummary:
    """How one species came out over the period."""

    species_name: str
    certificates: int
    mean_germination: int | None
    lowest_germination: int | None

    @property
    def had_germinations(self) -> bool:
        return self.mean_germination is not None


@dataclass(frozen=True)
class Turnaround:
    """How long jobs took, in days from booking in to issuing."""

    jobs: int
    fastest: int
    median: int
    slowest: int

    def describe(self) -> str:
        return f"{self.jobs} jobs, {self.fastest} to {self.slowest} days, median {self.median}"


def by_month(
    certificates: CertificateRepository,
    *,
    start: date,
    end: date,
) -> tuple[MonthlyCount, ...]:
    """Certificates issued per month, in order, with no gaps left out.

    A month with nothing in it is a row of zeroes rather than a missing row.
    The shape of the year is the point, and a missing row reads as a month
    somebody forgot to run the report for.
    """
    issued: Counter[tuple[int, int]] = Counter()
    withdrawn: Counter[tuple[int, int]] = Counter()

    for certificate in certificates.issued_between(start, end):
        key = (certificate.issued_on.year, certificate.issued_on.month)
        issued[key] += 1
        if certificate.is_withdrawn:
            withdrawn[key] += 1

    return tuple(
        MonthlyCount(
            year=year,
            month=month,
            issued=issued.get((year, month), 0),
            withdrawn=withdrawn.get((year, month), 0),
        )
        for year, month in _months(start, end)
    )


def by_species(
    certificates: CertificateRepository,
    *,
    start: date,
    end: date,
) -> tuple[SpeciesSummary, ...]:
    """One row per species, busiest first.

    The mean germination is over the certificates that carry one. A species
    where half the jobs were purity only would otherwise read as though its
    seed germinated at half the rate.
    """
    counts: Counter[str] = Counter()
    germinations: defaultdict[str, list[int]] = defaultdict(list)

    for certificate in certificates.issued_between(start, end):
        counts[certificate.species_name] += 1
        percent = certificate.results.germination_percent
        if percent is not None:
            germinations[certificate.species_name].append(percent)

    summaries = [
        SpeciesSummary(
            species_name=name,
            certificates=count,
            mean_germination=_mean(germinations[name]),
            lowest_germination=min(germinations[name]) if germinations[name] else None,
        )
        for name, count in counts.items()
    ]

    return tuple(sorted(summaries, key=lambda item: (-item.certificates, item.species_name)))


def turnaround(
    lots: LotRepository,
    certificates: CertificateRepository,
    *,
    start: date,
    end: date,
) -> Turnaround | None:
    """How long jobs took, or nothing when there were none.

    Measured from the day the lot was booked in to the day its first
    certificate went out. A second certificate on the same lot is a reissue
    and does not start the clock again.
    """
    first_issue: dict[str, Certificate] = {}
    for certificate in certificates.issued_between(start, end):
        held = first_issue.get(certificate.lot_reference)
        if held is None or certificate.issued_on < held.issued_on:
            first_issue[certificate.lot_reference] = certificate

    days: list[int] = []
    for reference, certificate in first_issue.items():
        booked = lots.booked_in_on(reference)
        if booked is None:
            continue
        days.append((certificate.issued_on - booked).days)

    if not days:
        return None

    days.sort()
    return Turnaround(
        jobs=len(days),
        fastest=days[0],
        median=days[len(days) // 2],
        slowest=days[-1],
    )


def _months(start: date, end: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month

    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1

    return months


def _mean(values: list[int]) -> int | None:
    if not values:
        return None
    total = Decimal(sum(values)) / Decimal(len(values))
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def kinds_issued(
    certificates: CertificateRepository,
    *,
    start: date,
    end: date,
) -> dict[CertificateKind, int]:
    """How many of each kind went out."""
    counts: Counter[CertificateKind] = Counter()
    for certificate in certificates.issued_between(start, end):
        counts[certificate.kind] += 1
    return dict(counts)
