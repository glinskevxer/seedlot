"""What a search for other species is, and what came out of it.

Three things have to travel together or the number means nothing: how many
seeds were found, how much seed was searched to find them, and whether the
search was looking for everything or only for a list. "Four wild oat seeds" is
not a result. "Four wild oat seeds in 1000 g, complete search" is.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from arc.quantities import weigh

__all__ = ["SearchKind", "Finding", "OtherSeedSearch"]


class SearchKind(Enum):
    """How wide the analyst was told to cast the net."""

    #: Every species that is not the one the lot was sold as.
    COMPLETE = "complete"
    #: Only the species the customer named, in the full working sample.
    LIMITED = "limited"
    #: Only the species the customer named, in a smaller sample than the full
    #: one. Cheaper, and much less able to find something rare.
    REDUCED = "reduced"

    @property
    def is_targeted(self) -> bool:
        """Whether the customer had to say what to look for."""
        return self is not SearchKind.COMPLETE

    @property
    def label(self) -> str:
        return f"{self.value} search"


@dataclass(frozen=True)
class Finding:
    """One species, and how many of its seeds were picked out."""

    species_name: str
    count: int

    def __post_init__(self) -> None:
        if not self.species_name.strip():
            raise ValueError("a finding has to name the species that was found")
        if self.count < 0:
            raise ValueError(f"{self.species_name} cannot have a negative count")

    @property
    def key(self) -> str:
        return self.species_name.strip().lower()


@dataclass(frozen=True)
class OtherSeedSearch:
    """One search through one working sample.

    A search with no findings is a real result and the common one. It is not
    the same as no search, which is why an empty findings tuple is allowed and
    an unrecorded weight is not.
    """

    species_name: str
    kind: SearchKind
    weight_examined_g: Decimal
    findings: tuple[Finding, ...] = ()
    sought: tuple[str, ...] = ()
    analyst: str = ""

    def __post_init__(self) -> None:
        if self.weight_examined_g <= 0:
            raise ValueError("a search has to say how much seed it went through")

    @property
    def nil_return(self) -> bool:
        """Whether nothing at all was found.

        A search that found a species and counted zero of it is still a nil
        return for that species, and the analyst who wrote the zero down said
        something the analyst who wrote nothing did not.
        """
        return sum(finding.count for finding in self.findings) == 0

    @property
    def total_found(self) -> int:
        return sum(finding.count for finding in self.findings)

    def count_of(self, species_name: str) -> int:
        """How many of one species were found, zero if it was not listed."""
        wanted = species_name.strip().lower()
        for finding in self.findings:
            if finding.key == wanted:
                return finding.count
        return 0

    def was_sought(self, species_name: str) -> bool:
        """Whether this species was one the search was actually looking for."""
        if self.kind is SearchKind.COMPLETE:
            return True
        wanted = species_name.strip().lower()
        return any(name.strip().lower() == wanted for name in self.sought)

    def rate_per_kg(self, species_name: str) -> Decimal:
        """The count scaled up to a kilogram, which is how buyers ask for it.

        Scaled, not measured. Four seeds in 250 g is sixteen per kilogram only
        in the sense that the arithmetic says so, and the certificate carries
        the weight examined next to it so the buyer can see how thin the
        evidence is.
        """
        found = Decimal(self.count_of(species_name))
        per_gram = found / self.weight_examined_g
        return weigh(per_gram * Decimal(1000), places=1)

    def describe(self) -> str:
        """One line for the worksheet."""
        examined = weigh(self.weight_examined_g, places=1)
        if self.nil_return:
            return f"none found in {examined} g, {self.kind.label}"

        parts = ", ".join(
            f"{finding.species_name} {finding.count}"
            for finding in self.findings
            if finding.count > 0
        )
        return f"{parts} in {examined} g, {self.kind.label}"
