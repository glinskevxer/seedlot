"""The registers the station has to be able to produce.

Three of them, and each exists because somebody outside the station asks for
it. The accreditation body wants the certificate register at audit. The office
wants the work in progress every Monday. The merchants want their own lots.

None of them recompute anything. A register that worked a germination out again
from the trays could disagree with the certificate that was already sent, and
the whole point of a register is that it says what was reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from arc.certificates.model import Certificate
from arc.lots.model import LotStatus, SeedLot
from arc.reporting.csv_writer import CsvWriter
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository

__all__ = [
    "certificate_register",
    "work_in_progress",
    "merchant_register",
    "WorkItem",
]


def certificate_register(
    certificates: CertificateRepository,
    *,
    start: date,
    end: date,
) -> str:
    """Every certificate issued in a stretch of dates, as the auditor wants it."""
    sheet = CsvWriter(
        [
            "number",
            "kind",
            "issued on",
            "lot",
            "species",
            "merchant",
            "origin",
            "weight kg",
            "pure seed",
            "germination",
            "germination tested",
            "withdrawn on",
            "supersedes",
        ]
    )

    for issued in certificates.issued_between(start, end):
        results = issued.results
        sheet.row(
            issued.number,
            issued.kind.value,
            issued.issued_on,
            issued.lot_reference,
            issued.species_name,
            issued.merchant,
            issued.origin_country,
            issued.lot_weight_kg,
            results.pure_seed,
            results.germination_percent,
            results.germination_tested_on,
            issued.withdrawn_on,
            issued.supersedes,
        )

    return sheet.to_csv()


@dataclass(frozen=True)
class WorkItem:
    """One lot on the Monday morning list."""

    lot: SeedLot
    certificates_issued: int

    @property
    def is_waiting_on_the_bench(self) -> bool:
        return self.lot.status in (LotStatus.SAMPLED, LotStatus.IN_TEST)


def work_in_progress(
    lots: LotRepository,
    certificates: CertificateRepository,
) -> tuple[WorkItem, ...]:
    """Every lot not yet closed, oldest first, with what has been issued on it."""
    return tuple(
        WorkItem(
            lot=lot,
            certificates_issued=len(certificates.for_lot(str(lot.reference))),
        )
        for lot in lots.open_lots()
    )


def merchant_register(
    lots: LotRepository,
    certificates: CertificateRepository,
    merchant: str,
) -> tuple[tuple[SeedLot, tuple[Certificate, ...]], ...]:
    """One merchant's lots and whatever has been issued against each.

    Matched on the name as it was written at booking in, because that is what
    the merchant put on their own paperwork and what they will quote back.
    """
    wanted = merchant.strip().lower()
    found: list[tuple[SeedLot, tuple[Certificate, ...]]] = []

    for lot in lots.open_lots():
        if lot.merchant.strip().lower() != wanted:
            continue
        found.append((lot, certificates.for_lot(str(lot.reference))))

    return tuple(found)
