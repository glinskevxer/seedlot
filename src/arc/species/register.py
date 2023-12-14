"""Looking a species up by whatever the customer wrote on the sample bag.

Merchants send seed in with the common name on the label, growers use whatever
their region calls it, and the certificate has to carry the botanical name. So
the register answers to all three and returns the one true entry, rather than
making whoever is booking the sample in translate first.

It refuses near misses on purpose. "wheat" is a species and "durum wheat" is a
different one the station is not accredited for, so a fuzzy match that quietly
returned the first would put the wrong working sample size on the worksheet.
"""

from __future__ import annotations

from collections.abc import Iterator

from arc.errors import ConfigurationError, NotFound
from arc.species.model import SeedClass, Species
from arc.species.table import SPECIES_TABLE

__all__ = ["SpeciesRegister", "register"]


class SpeciesRegister:
    """Every species the station will accept, indexed by all its names."""

    def __init__(self, entries: tuple[Species, ...] = SPECIES_TABLE) -> None:
        self._entries = entries
        self._by_name: dict[str, Species] = {}

        for entry in entries:
            for name in entry.names():
                clash = self._by_name.get(name)
                if clash is not None and clash is not entry:
                    raise ConfigurationError(
                        f"{name!r} is claimed by both {clash.botanical_name} "
                        f"and {entry.botanical_name}"
                    )
                self._by_name[name] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[Species]:
        return iter(self._entries)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self._normalise(name) in self._by_name

    def find(self, name: str) -> Species | None:
        """The species, or nothing. Use this when not finding one is expected."""
        return self._by_name.get(self._normalise(name))

    def require(self, name: str) -> Species:
        """The species, or a refusal naming what was asked for."""
        found = self.find(name)
        if found is None:
            raise NotFound("species", name)
        return found

    def in_class(self, seed_class: SeedClass) -> tuple[Species, ...]:
        return tuple(entry for entry in self._entries if entry.seed_class is seed_class)

    def chaffy(self) -> tuple[Species, ...]:
        """The awkward ones: light, hairy or winged seed that will not sit still."""
        return tuple(entry for entry in self._entries if entry.chaffy)

    def names(self) -> tuple[str, ...]:
        """Every botanical name, sorted, for the listing the CLI prints."""
        return tuple(sorted(entry.botanical_name for entry in self._entries))

    def suggest(self, name: str) -> tuple[str, ...]:
        """Names that start the same way, to put under a not found message.

        Prefix matching only. Anything cleverer starts guessing, and guessing a
        species is how a sample gets tested against the wrong table.
        """
        wanted = self._normalise(name)
        if not wanted:
            return ()
        hits = {
            entry.botanical_name
            for known, entry in self._by_name.items()
            if known.startswith(wanted)
        }
        return tuple(sorted(hits))

    @staticmethod
    def _normalise(name: str) -> str:
        return " ".join(name.strip().lower().split())


#: The register the rest of the package uses. Built once at import.
register = SpeciesRegister()
