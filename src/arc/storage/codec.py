"""Turning the station's values into columns and back.

SQLite has five types and none of them is a decimal, a date or an enumeration.
Everything here is about crossing that gap without losing anything on the way.

Decimals are stored as text. Storing them as REAL would turn 98.4 into
98.400000000000006 and a purity analysis that no longer sums to a hundred, and
storing them as integer pence loses the number of decimal places the weighing
was made to, which is itself part of the record.

Dates are stored as ISO text, which sorts correctly as a string, so a query for
everything booked in this year is a comparison rather than a conversion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TypeVar

__all__ = [
    "to_text",
    "to_decimal",
    "to_optional_decimal",
    "to_iso",
    "to_date",
    "to_optional_date",
    "to_bool",
    "from_bool",
    "to_enum",
]


def to_text(value: Decimal) -> str:
    """A decimal as it will be stored, keeping every place it was written to."""
    return format(value, "f")


def to_decimal(value: str) -> Decimal:
    return Decimal(value)


def to_optional_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def to_iso(value: date) -> str:
    return value.isoformat()


def to_date(value: str) -> date:
    return date.fromisoformat(value)


def to_optional_date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def from_bool(value: bool) -> int:
    """SQLite has no boolean, so it goes in as the integer everyone uses."""
    return 1 if value else 0


def to_bool(value: int) -> bool:
    return bool(value)


EnumT = TypeVar("EnumT", bound=Enum)


def to_enum(enum_class: type[EnumT], value: str) -> EnumT:
    """Reads an enumeration back from the value it was stored under.

    Stored by value rather than by name, because the values are the words that
    appear on the worksheet and a rename of a member should be caught here
    rather than silently reading as something else.
    """
    for member in enum_class:
        if member.value == value:
            return member
    raise ValueError(f"{value!r} is not a {enum_class.__name__}")
