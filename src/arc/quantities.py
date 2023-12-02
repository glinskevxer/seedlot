"""Weights and percentages, weighed and rounded the way the handbook says.

Two rules live here and both of them look like fussiness until you have seen a
certificate rejected over them.

The first is that how finely a sample is weighed depends on how heavy it is.
A ten gram working sample is weighed to three decimal places and a one kilogram
one to whole grams, because weighing the kilogram to milligrams claims a
precision the balance does not have and weighing the ten grams to whole grams
throws away the only precision that matters.

The second is that the components of a purity analysis have to add up to
exactly one hundred. They will not, once each has been rounded on its own, so
the largest one absorbs the difference. Doing it any other way produces a
certificate whose figures do not sum, which is the single most common reason a
certificate comes back.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

__all__ = [
    "Grams",
    "decimals_for",
    "weigh",
    "Percentage",
    "as_percentages",
    "normalise_to_hundred",
]

#: Weight bands and the number of decimal places each is weighed to. Read as
#: "below this many grams, use this many decimals", lightest band first.
_WEIGHING_BANDS: tuple[tuple[Decimal, int], ...] = (
    (Decimal("1"), 4),
    (Decimal("10"), 3),
    (Decimal("100"), 2),
    (Decimal("1000"), 1),
)

#: Anything at or above the last band is weighed to whole grams.
_HEAVIEST_DECIMALS = 0

Grams = Decimal


def decimals_for(weight: Grams) -> int:
    """How many decimal places a sample of this weight is weighed to.

    The band is chosen on the weight itself, so a sample that turns out
    lighter than expected is weighed more finely than one that turns out
    heavier. That is the point: the decision follows the sample, not the plan.
    """
    if weight < 0:
        raise ValueError("a weight is never negative")
    for ceiling, places in _WEIGHING_BANDS:
        if weight < ceiling:
            return places
    return _HEAVIEST_DECIMALS


def weigh(weight: Grams, *, places: int | None = None) -> Grams:
    """Rounds a weight to the precision its own band allows.

    Pass ``places`` only when the band has already been decided by something
    else, which happens when every component of one analysis has to be weighed
    at the precision the whole sample set.
    """
    if places is None:
        places = decimals_for(weight)
    quantum = Decimal(1).scaleb(-places)
    return weight.quantize(quantum, rounding=ROUND_HALF_UP)


class Percentage:
    """A percentage carried to one decimal place, which is how they are reported."""

    __slots__ = ("_value",)

    def __init__(self, value: Decimal | int | str) -> None:
        as_decimal = Decimal(str(value))
        if as_decimal < 0 or as_decimal > 100:
            raise ValueError(f"a percentage runs from 0 to 100, not {as_decimal}")
        self._value = as_decimal.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def value(self) -> Decimal:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Percentage):
            return self._value == other._value
        return NotImplemented

    def __lt__(self, other: Percentage) -> bool:
        return self._value < other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"Percentage('{self._value}')"

    def __str__(self) -> str:
        return f"{self._value}"


def as_percentages(weights: Sequence[Grams], total: Grams) -> list[Decimal]:
    """Each weight as a percentage of the total, unrounded.

    Kept separate from the rounding so that the adjustment below has the full
    precision to work from. Rounding first and adjusting afterwards moves the
    difference onto whichever component happened to round up.
    """
    if total <= 0:
        raise ValueError("cannot take percentages of nothing")
    return [(weight / total) * Decimal(100) for weight in weights]


def normalise_to_hundred(values: Iterable[Decimal]) -> list[Percentage]:
    """Rounds each value to one decimal and makes the set add up to 100.0.

    The difference goes on the largest component, which is what the handbook
    says and is also the only choice that cannot change which component is
    largest. Putting it on the smallest can turn a 0.0 into a 0.1 and invent a
    contaminant that was never there.
    """
    unrounded = list(values)
    if not unrounded:
        return []

    rounded = [value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) for value in unrounded]
    drift = Decimal("100.0") - sum(rounded)
    if drift != 0:
        largest = max(range(len(rounded)), key=lambda index: rounded[index])
        rounded[largest] += drift

    return [Percentage(value) for value in rounded]
