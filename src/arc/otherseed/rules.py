"""What makes a search reportable, and what quietly makes it worthless.

The dangerous result here is not a wrong count. It is a right count taken from
too little seed, or a count of something nobody was looking for, reported as
though the search would have found it wherever it was. Both read as a clean
number on the certificate and neither is one, so both are refused here rather
than explained in a note.
"""

from __future__ import annotations

from decimal import Decimal

from arc.errors import Rule
from arc.otherseed.model import OtherSeedSearch, SearchKind
from arc.quantities import weigh
from arc.species.model import Species

__all__ = [
    "REDUCED_FRACTION",
    "WEIGHT_TOLERANCE",
    "required_weight_g",
    "check_search",
]

#: A reduced search goes through a fifth of the full working sample. Less than
#: that and a species present at a low rate is more likely to be missed than
#: found, which makes the nil return misleading rather than merely weak.
REDUCED_FRACTION = Decimal("0.2")

#: The balance and the divider between them will not land on the nominal weight
#: exactly. Half a percent under is the bench reality and is not a short search.
WEIGHT_TOLERANCE = Decimal("0.005")


def required_weight_g(species: Species, kind: SearchKind) -> Decimal:
    """How much seed this kind of search has to go through for this species."""
    full = species.other_seed_working_sample_g
    if kind is SearchKind.REDUCED:
        return weigh(full * REDUCED_FRACTION, places=1)
    return weigh(full, places=1)


def check_search(search: OtherSeedSearch, species: Species) -> list[Rule]:
    """Everything wrong with a search, in the order a person would notice it."""
    broken: list[Rule] = []
    subject = search.species_name

    required = required_weight_g(species, search.kind)
    floor = required * (Decimal(1) - WEIGHT_TOLERANCE)
    if search.weight_examined_g < floor:
        short_by = weigh(required - search.weight_examined_g, places=1)
        broken.append(
            Rule(
                "OTHER_SEED_SAMPLE_SHORT",
                f"a {search.kind.value} search on {species.common_name} needs "
                f"{required} g and this one went through "
                f"{weigh(search.weight_examined_g, places=1)} g, "
                f"{short_by} g short",
                subject,
            )
        )

    if search.kind.is_targeted and not search.sought:
        broken.append(
            Rule(
                "OTHER_SEED_NOTHING_SOUGHT",
                f"a {search.kind.value} search only covers the species it was "
                "asked to look for, so it has to name them",
                subject,
            )
        )

    if search.kind is SearchKind.COMPLETE and search.sought:
        # Naming species on a complete search is how a limited search gets
        # reported as a complete one by accident.
        broken.append(
            Rule(
                "OTHER_SEED_COMPLETE_IS_NOT_TARGETED",
                "a complete search covers everything, so it cannot also carry "
                "a list of what to look for",
                subject,
            )
        )

    seen: set[str] = set()
    for finding in search.findings:
        if finding.key in seen:
            broken.append(
                Rule(
                    "OTHER_SEED_COUNTED_TWICE",
                    f"{finding.species_name} appears twice in one search",
                    subject,
                )
            )
        seen.add(finding.key)

        if finding.key == species.botanical_name.lower():
            broken.append(
                Rule(
                    "OTHER_SEED_IS_THE_CROP",
                    f"{finding.species_name} is what the lot was sold as, so it "
                    "is pure seed and belongs in the purity analysis",
                    subject,
                )
            )

        if not search.was_sought(finding.species_name):
            broken.append(
                Rule(
                    "OTHER_SEED_NOT_SOUGHT",
                    f"{finding.species_name} was found but was not on the list "
                    f"for this {search.kind.value} search, so the count cannot "
                    "be reported as a rate",
                    subject,
                )
            )

    if not search.analyst.strip():
        broken.append(
            Rule(
                "OTHER_SEED_UNSIGNED",
                "a search has to carry the name of whoever did the counting",
                subject,
            )
        )

    return broken
