"""The certificate: the only thing that leaves the building.

Everything else the station does is working. The certificate is the product,
it travels with the seed across borders, and somebody who has never met anyone
here will make a purchase decision on it. So the rules about what may go on one
are stricter than the rules about anything else.

Two of them are worth stating plainly.

A certificate carries only determinations that were actually made. There is no
such thing as a germination of zero because nobody tested it; the field is
absent, and absent and zero look nothing alike to a buyer.

A certificate is never edited. A figure that turns out wrong is corrected by
issuing a replacement that names the certificate it supersedes, because the
original is already in somebody's file and the two have to be reconcilable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from arc.errors import Rule
from arc.quantities import Percentage

__all__ = [
    "CertificateKind",
    "CertificateNumber",
    "Determinations",
    "Certificate",
    "GERMINATION_VALID_FOR",
    "check_certificate",
]

#: How long a germination figure may be quoted before it has to be redone.
GERMINATION_VALID_FOR = timedelta(days=365)

_NUMBER = re.compile(r"^(?P<station>[A-Z]{2}-\d{4})/(?P<year>\d{4})/(?P<serial>\d{5})$")


class CertificateKind(Enum):
    """Which certificate this is.

    An orange one follows seed across a border and carries every determination
    the handbook requires. A blue one covers a lot that has been sampled but not
    fully tested, and a green one reports a single determination for a customer
    who asked for one thing.
    """

    ORANGE_INTERNATIONAL = "orange international seed lot"
    BLUE_INTERNATIONAL = "blue international sample"
    GREEN_ANALYSIS = "green analysis report"

    @property
    def crosses_borders(self) -> bool:
        return self is CertificateKind.ORANGE_INTERNATIONAL

    @property
    def requires_full_analysis(self) -> bool:
        """The orange one is the only kind that needs everything on it."""
        return self is CertificateKind.ORANGE_INTERNATIONAL


@dataclass(frozen=True, order=True)
class CertificateNumber:
    """Station, year and serial, as printed at the top of the sheet."""

    station: str
    year: int
    serial: int

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z]{2}-\d{4}", self.station):
            raise ValueError(f"{self.station!r} is not a station code")
        if not 2000 <= self.year <= 2099:
            raise ValueError(f"{self.year} is not a year this station has worked")
        if not 1 <= self.serial <= 99999:
            raise ValueError("a certificate serial runs from 1 to 99999")

    @classmethod
    def parse(cls, text: str) -> CertificateNumber:
        match = _NUMBER.match(text.strip().upper())
        if match is None:
            raise ValueError(
                f"{text!r} is not a certificate number, expected GB-0214/2024/00187"
            )
        return cls(
            station=match.group("station"),
            year=int(match.group("year")),
            serial=int(match.group("serial")),
        )

    def __str__(self) -> str:
        return f"{self.station}/{self.year:04d}/{self.serial:05d}"


@dataclass(frozen=True)
class Determinations:
    """What was determined. Anything not determined is absent, never zero.

    Called this rather than the obvious name because pytest collects anything
    beginning with Test as a test class, and a dataclass with a constructor
    then produces a warning on every run until somebody goes looking.
    """

    pure_seed: Percentage | None = None
    other_seed: Percentage | None = None
    inert_matter: Percentage | None = None
    germination_percent: int | None = None
    germination_tested_on: date | None = None
    hard_seed_percent: int | None = None
    moisture_percent: Decimal | None = None
    thousand_seed_weight_g: Decimal | None = None
    other_species_found: tuple[str, ...] = ()

    @property
    def has_purity(self) -> bool:
        return self.pure_seed is not None

    @property
    def has_germination(self) -> bool:
        return self.germination_percent is not None

    def determinations(self) -> tuple[str, ...]:
        """The names of everything that was actually done."""
        done: list[str] = []
        if self.has_purity:
            done.append("purity")
        if self.has_germination:
            done.append("germination")
        if self.moisture_percent is not None:
            done.append("moisture")
        if self.thousand_seed_weight_g is not None:
            done.append("thousand seed weight")
        return tuple(done)


@dataclass(frozen=True)
class Certificate:
    """One certificate, as issued."""

    number: CertificateNumber
    kind: CertificateKind
    lot_reference: str
    species_name: str
    merchant: str
    origin_country: str
    lot_weight_kg: Decimal
    results: Determinations
    issued_on: date
    signed_by: str
    supersedes: CertificateNumber | None = field(default=None)
    withdrawn_on: date | None = field(default=None)

    @property
    def is_withdrawn(self) -> bool:
        return self.withdrawn_on is not None

    @property
    def is_replacement(self) -> bool:
        return self.supersedes is not None

    def germination_valid_until(self) -> date | None:
        """When the germination figure stops being quotable."""
        tested = self.results.germination_tested_on
        if tested is None:
            return None
        return tested + GERMINATION_VALID_FOR

    def germination_current_on(self, day: date) -> bool:
        """Whether the germination figure may still be quoted on that day."""
        expires = self.germination_valid_until()
        if expires is None:
            return False
        return day <= expires


def check_certificate(certificate: Certificate) -> list[Rule]:
    """Whether this certificate may be issued at all."""
    broken: list[Rule] = []
    subject = str(certificate.number)
    results = certificate.results

    if certificate.kind.requires_full_analysis:
        if not results.has_purity:
            broken.append(
                Rule(
                    "PURITY_MISSING",
                    "an orange certificate carries a purity analysis and this has none",
                    subject,
                )
            )
        if not results.has_germination:
            broken.append(
                Rule(
                    "GERMINATION_MISSING",
                    "an orange certificate carries a germination and this has none",
                    subject,
                )
            )

    if results.has_purity:
        total = (
            results.pure_seed.value  # type: ignore[union-attr]
            + results.other_seed.value  # type: ignore[union-attr]
            + results.inert_matter.value  # type: ignore[union-attr]
        )
        if total != Decimal("100.0"):
            broken.append(
                Rule(
                    "PURITY_DOES_NOT_SUM",
                    f"the purity components add up to {total} and not to 100.0",
                    subject,
                )
            )

    if results.has_germination and results.germination_tested_on is None:
        broken.append(
            Rule(
                "GERMINATION_UNDATED",
                "a germination figure is only quotable for a year, so it has to "
                "carry the date it was tested",
                subject,
            )
        )

    if results.germination_tested_on is not None:
        if results.germination_tested_on > certificate.issued_on:
            broken.append(
                Rule(
                    "GERMINATION_AFTER_ISSUE",
                    "the germination is dated after the certificate was issued",
                    subject,
                )
            )

    return broken
