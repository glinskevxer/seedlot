"""Issuing a certificate from what the station actually did.

This is the last step and the one with the most ways to go wrong, because it is
where working turns into a claim. The rule underneath all of it is that the
certificate reports what was determined and nothing else. If the germination
was never done, the field is absent; if the purity was done twice and the two
disagree, there is no certificate at all until somebody decides which stands.

The determinations are gathered from what was recorded rather than passed in.
Letting a caller hand over a germination percentage would make it possible to
certify a figure that is not in the database, and the database is what an audit
reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
    check_certificate,
)
from arc.errors import RuleBroken, Rule
from arc.germination.outcome import decide
from arc.lots.model import LotStatus
from arc.purity.tolerance import compare
from arc.quantities import Percentage
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository

__all__ = ["gather", "issue"]


@dataclass(frozen=True)
class Gathered:
    """Everything the station has on a lot, and whether it hangs together."""

    results: Determinations
    problems: tuple[Rule, ...]

    @property
    def is_ready(self) -> bool:
        return not self.problems


def gather(
    lot_reference: str,
    *,
    purity: PurityRepository,
    germination: GerminationRepository,
) -> Gathered:
    """Pulls the recorded determinations together into one set of results.

    Duplicate purity analyses are compared here rather than at the bench,
    because it is only at issuing time that both of them certainly exist.
    """
    problems: list[Rule] = []

    pure = other = inert = None
    analyses = [stored for stored in purity.for_lot(lot_reference) if stored.was_computed]

    if analyses:
        latest = analyses[-1]
        pure = Percentage(latest.pure_seed_percent)  # type: ignore[arg-type]
        other = Percentage(latest.other_seed_percent)  # type: ignore[arg-type]
        inert = Percentage(latest.inert_percent)  # type: ignore[arg-type]

        if len(analyses) >= 2:
            first, second = analyses[-2], analyses[-1]
            species = register.find(_species_of(first.lot_reference))
            chaffy = bool(species and species.chaffy)
            check = compare(
                first.pure_seed_percent,  # type: ignore[arg-type]
                second.pure_seed_percent,  # type: ignore[arg-type]
                chaffy=chaffy,
            )
            if not check.compatible:
                problems.append(
                    Rule(
                        "PURITY_DUPLICATES_DISAGREE",
                        f"the two purity analyses do not agree: {check.explain()}",
                        lot_reference,
                    )
                )

    germination_percent = None
    tested_on = None
    tests = germination.for_lot(lot_reference)

    if tests:
        outcome = decide(tests[0], tests[1] if len(tests) > 1 else None)
        if outcome.verdict.is_final:
            germination_percent = outcome.reported_percent
            tested_on = tests[-1].final_count_on
        else:
            problems.append(
                Rule(
                    "GERMINATION_NOT_SETTLED",
                    f"the germination is not settled: {outcome.reason}",
                    lot_reference,
                )
            )

    return Gathered(
        results=Determinations(
            pure_seed=pure,
            other_seed=other,
            inert_matter=inert,
            germination_percent=germination_percent,
            germination_tested_on=tested_on,
        ),
        problems=tuple(problems),
    )


def issue(
    lot_reference: str,
    kind: CertificateKind,
    *,
    signed_by: str,
    on: date,
    lots: LotRepository,
    purity: PurityRepository,
    germination: GerminationRepository,
    certificates: CertificateRepository,
) -> Certificate:
    """Issues a certificate for a lot, or refuses with every reason it cannot.

    The lot is moved to reported as part of the same call. A certificate that
    exists against a lot still marked in test is the kind of inconsistency
    nobody notices until an audit asks for the two to be reconciled.
    """
    lot = lots.require(lot_reference)
    gathered = gather(lot_reference, purity=purity, germination=germination)

    number = CertificateNumber(
        station=_station_code(),
        year=on.year,
        serial=certificates.next_serial(on.year),
    )

    certificate = Certificate(
        number=number,
        kind=kind,
        lot_reference=str(lot.reference),
        species_name=lot.species_name,
        merchant=lot.merchant,
        origin_country=lot.origin_country,
        lot_weight_kg=lot.declared_weight_kg,
        results=gathered.results,
        issued_on=on,
        signed_by=signed_by,
    )

    problems = list(gathered.problems) + check_certificate(certificate)
    if problems:
        raise RuleBroken(problems)

    certificates.issue(certificate)

    if lot.status is LotStatus.IN_TEST:
        lot.move_to(LotStatus.REPORTED)
        lots.save(lot, booked_in_on=on)

    return certificate


def _station_code() -> str:
    from arc import STATION_CODE

    return STATION_CODE


def _species_of(lot_reference: str) -> str:
    # The stored analysis does not carry the species, so the lot does. Kept as
    # its own function because the day a lot can hold two species this is the
    # line that has to change.
    return lot_reference
