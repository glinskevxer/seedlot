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
    OtherSeedCount,
    OtherSeedReport,
    check_certificate,
)
from arc.errors import Rule, RuleBroken
from arc.germination.dormancy import check_treatment
from arc.germination.outcome import decide
from arc.purity.tolerance import compare
from arc.quantities import Percentage
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.otherseed import OtherSeedRepository, StoredSearch
from arc.storage.physical import MoistureRepository, SeedWeightRepository
from arc.storage.retention import RetentionRepository
from arc.workflow.progress import mark_reported
from arc.workflow.retaining import retain

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
    species_name: str,
    *,
    purity: PurityRepository,
    germination: GerminationRepository,
    moisture: MoistureRepository | None = None,
    seed_weight: SeedWeightRepository | None = None,
    other_seed: OtherSeedRepository | None = None,
) -> Gathered:
    """Pulls the recorded determinations together into one set of results.

    Duplicate purity analyses are compared here rather than at the bench,
    because it is only at issuing time that both of them certainly exist.

    The species has to be passed in. The purity rows do not carry it and the
    duplicate tolerance is a different number for chaffy seed, so working it
    out from anything to hand here would mean holding grass to the allowance
    for wheat.
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
            species = register.require(species_name)
            chaffy = species.chaffy
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
    treatment = None
    tests = germination.for_lot(lot_reference)

    if tests:
        reported = tests[-1]
        problems.extend(check_treatment(reported, register.require(species_name)))

        outcome = decide(tests[0], tests[1] if len(tests) > 1 else None)
        if outcome.verdict.is_final:
            germination_percent = outcome.reported_percent
            tested_on = reported.final_count_on
            treatment = reported.treatment
        else:
            problems.append(
                Rule(
                    "GERMINATION_NOT_SETTLED",
                    f"the germination is not settled: {outcome.reason}",
                    lot_reference,
                )
            )

    moisture_percent = None if moisture is None else moisture.reportable_for_lot(lot_reference)

    thousand_seed_weight = None
    if seed_weight is not None:
        weighing = seed_weight.latest_for_lot(lot_reference)
        if weighing is not None:
            if weighing.within_tolerance:
                thousand_seed_weight = weighing.grams_per_thousand
            else:
                problems.append(
                    Rule(
                        "SEED_WEIGHT_SCATTER_TOO_WIDE",
                        f"the thousand seed weight cannot be reported: {weighing.explain()}",
                        lot_reference,
                    )
                )

    other_seed_report = None
    if other_seed is not None:
        searched = other_seed.latest_for_lot(lot_reference)
        if searched is not None:
            other_seed_report = _report_from(searched)

    return Gathered(
        results=Determinations(
            pure_seed=pure,
            other_seed=other,
            inert_matter=inert,
            germination_percent=germination_percent,
            germination_tested_on=tested_on,
            germination_treatment=treatment,
            moisture_percent=moisture_percent,
            thousand_seed_weight_g=thousand_seed_weight,
            other_seed_report=other_seed_report,
        ),
        problems=tuple(problems),
    )


def _report_from(stored: StoredSearch) -> OtherSeedReport:
    """Turns a recorded search into the shape the certificate carries.

    The rate per kilogram is worked out here rather than stored, because it is
    the count and the weight examined that were measured and the rate is only
    ever arithmetic on the two. Storing it would give a later change to the
    rounding somewhere to hide.
    """
    search = stored.search
    return OtherSeedReport(
        kind=search.kind.value,
        weight_examined_g=search.weight_examined_g,
        counts=tuple(
            OtherSeedCount(
                species_name=finding.species_name,
                count=finding.count,
                per_kg=search.rate_per_kg(finding.species_name),
            )
            for finding in search.findings
        ),
        sought=search.sought,
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
    moisture: MoistureRepository | None = None,
    seed_weight: SeedWeightRepository | None = None,
    other_seed: OtherSeedRepository | None = None,
    retention: RetentionRepository | None = None,
) -> Certificate:
    """Issues a certificate for a lot, or refuses with every reason it cannot.

    The lot is moved to reported as part of the same call. A certificate that
    exists against a lot still marked in test is the kind of inconsistency
    nobody notices until an audit asks for the two to be reconciled.
    """
    lot = lots.require(lot_reference)
    gathered = gather(
        lot_reference,
        lot.species_name,
        purity=purity,
        germination=germination,
        moisture=moisture,
        seed_weight=seed_weight,
        other_seed=other_seed,
    )

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

    if retention is not None:
        retain(certificate, register.require(lot.species_name), retention, on=on)

    mark_reported(lot, lots, on=on)

    return certificate


def _station_code() -> str:
    from arc import STATION_CODE

    return STATION_CODE
