"""Putting the remainder of the sample away when the certificate goes out.

The weight that goes into the store is worked out rather than weighed, and it
is worth being plain about why. Nobody puts the jar on a balance at the end of
a job; the analyst tips what is left back in and writes the lot number on the
lid. What the station can say with confidence is how much seed arrived and
which determinations were done, and every determination has a working sample
size in the handbook.

So the figure here is the submitted sample less what the work took. It is an
upper bound on what is really in the jar rather than a measurement, which is
the safe direction to be wrong in: the store may turn out to hold less than
this and the repeat is refused at the bench, but it will never think a jar is
empty when there is seed in it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from arc.certificates.model import Certificate
from arc.retention.model import Determination, RetainedSample
from arc.retention.rules import needed_for
from arc.species.model import Species
from arc.storage.retention import RetentionRepository

__all__ = ["consumed_by", "retain"]

#: Which determination on a certificate accounts for which draw.
#:
#: The search for other species is deliberately not here. Its working sample is
#: ten times the purity one, which for wheat is 1200 g against a submitted
#: sample of 1000 g, so it cannot have come out of the same bag and does not:
#: a customer ordering the search sends a separate, larger sample for it.
#: Deducting it from the standard sample made the jar read as empty after
#: every search, which is how this was noticed.
_BY_NAME: dict[str, Determination] = {
    "purity": Determination.PURITY,
    "germination": Determination.GERMINATION,
    "moisture": Determination.MOISTURE,
    "thousand seed weight": Determination.THOUSAND_SEED_WEIGHT,
}


def consumed_by(certificate: Certificate, species: Species) -> Decimal:
    """How much seed the work behind this certificate took.

    A germination that was repeated took two working samples, and the
    certificate does not carry that. This counts each determination once,
    which is the same upper bound the module docstring is about: the store is
    told it holds no more than this.
    """
    total = Decimal("0")
    for name in certificate.results.determinations():
        determination = _BY_NAME.get(name)
        if determination is not None:
            total += needed_for(determination, species)
    return total


def retain(
    certificate: Certificate,
    species: Species,
    store: RetentionRepository,
    *,
    on: date,
) -> RetainedSample:
    """Puts what is left of the sample into the store against the certificate.

    Called as part of issuing rather than afterwards, because a certificate
    with no sample behind it is a claim the station cannot defend, and the
    moment to notice that is while the certificate is still being made.
    """
    left = species.submitted_sample_g - consumed_by(certificate, species)
    if left < 0:
        left = Decimal("0")

    sample = RetainedSample(
        lot_reference=certificate.lot_reference,
        species_name=species.botanical_name,
        remaining_g=left,
        held_from=on,
        certificate_kind=certificate.kind,
    )
    store.place(sample)
    return sample
