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

from arc.certificates.model import Certificate, OtherSeedReport
from arc.lots.model import LotStatus, SeedLot
from arc.otherseed.model import OtherSeedSearch
from arc.reporting.csv_writer import CsvWriter
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository
from arc.storage.retention import RetentionRepository

__all__ = [
    "certificate_register",
    "work_in_progress",
    "merchant_register",
    "other_seed_register",
    "store_register",
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
            "other seed searched g",
            "other seed found",
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
            None
            if results.other_seed_report is None
            else results.other_seed_report.weight_examined_g,
            _found_summary(results.other_seed_report),
            issued.withdrawn_on,
            issued.supersedes,
        )

    return sheet.to_csv()


def _found_summary(report: OtherSeedReport | None) -> str | None:
    """What went in the found column, or nothing when no search was done.

    An empty cell means nobody searched. A cell reading "none" means somebody
    searched and found nothing, which is a much stronger statement and the one
    a merchant is buying.
    """
    if report is None:
        return None
    if report.is_nil:
        return "none"
    return ", ".join(
        f"{found.species_name} {found.count}" for found in report.counts if found.count > 0
    )


def other_seed_register(
    lots: LotRepository,
    searches: OtherSeedRepository,
) -> str:
    """Every search the station has done, whatever came of it.

    Kept separate from the certificate register because a search is often
    ordered on its own, and because the accreditation body asks for the
    searches by species found rather than by certificate.
    """
    sheet = CsvWriter(
        [
            "lot",
            "species",
            "merchant",
            "searched on",
            "kind",
            "weight examined g",
            "sought",
            "found",
            "analyst",
        ]
    )

    for lot in lots.open_lots():
        for stored in searches.for_lot(str(lot.reference)):
            search = stored.search
            sheet.row(
                lot.reference,
                lot.species_name,
                lot.merchant,
                stored.searched_on,
                search.kind.value,
                search.weight_examined_g,
                "; ".join(search.sought),
                "none" if search.nil_return else _findings_summary(search),
                search.analyst,
            )

    return sheet.to_csv()


def _findings_summary(search: OtherSeedSearch) -> str:
    return ", ".join(
        f"{finding.species_name} {finding.count}"
        for finding in search.findings
        if finding.count > 0
    )


def store_register(
    retention: RetentionRepository,
    *,
    on: date,
) -> str:
    """Everything the sample store is holding, and how close it is to going.

    Sorted by how long is left rather than by lot, because the person reading
    it is standing in front of the shelves deciding what to pull, and the ones
    at the top are the ones they came for.
    """
    sheet = CsvWriter(
        [
            "lot",
            "species",
            "remaining g",
            "held from",
            "hold until",
            "days left",
            "certificate",
            "due",
        ]
    )

    held = sorted(retention.held(), key=lambda sample: sample.hold_until)

    for sample in held:
        kind = sample.certificate_kind
        sheet.row(
            sample.lot_reference,
            sample.species_name,
            sample.remaining_g,
            sample.held_from,
            sample.hold_until,
            sample.days_left_on(on),
            "none" if kind is None else kind.value,
            "yes" if sample.is_due_for_disposal_on(on) else "no",
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
    return tuple(
        (lot, certificates.for_lot(str(lot.reference))) for lot in lots.for_merchant(merchant)
    )
