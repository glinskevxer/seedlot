"""The failures the station raises on purpose.

Everything the laboratory refuses to do falls into one of four shapes, and the
distinction matters because they are answered differently. A rule that was
broken is written on the worksheet and the analyst is told; a lookup that found
nothing is a typo at the bench; a state error means somebody worked a sample
out of order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ArcError",
    "NotFound",
    "RuleBroken",
    "Rule",
    "OutOfOrder",
    "ConfigurationError",
]


@dataclass(frozen=True)
class Rule:
    """One rule that was not satisfied.

    The ``code`` is stable and is what the worksheet, the report and the tests
    all key on. The ``detail`` is a sentence for whoever is standing at the
    bench, and is allowed to change wording without anything breaking.
    """

    code: str
    detail: str
    subject: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("a rule needs a code")
        if not self.detail:
            raise ValueError("a rule needs a detail line")

    def __str__(self) -> str:
        if self.subject is None:
            return f"{self.code}: {self.detail}"
        return f"{self.code} ({self.subject}): {self.detail}"


class ArcError(Exception):
    """Base for everything this package raises deliberately."""


class NotFound(ArcError):
    """A lookup by identifier found nothing."""

    def __init__(self, what: str, identifier: object) -> None:
        super().__init__(f"no {what} called {identifier!r}")
        self.what = what
        self.identifier = identifier


class OutOfOrder(ArcError):
    """A step was taken before the step it depends on."""


class ConfigurationError(ArcError):
    """The station is set up wrongly, and no amount of retrying will help."""


@dataclass
class RuleBroken(ArcError):
    """One or more rules said no.

    A germination test can fail several checks at once and the analyst needs
    all of them before they redo anything, so this carries a list rather than
    a single reason.
    """

    rules: list[Rule] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rules:
            raise ValueError("a refusal needs at least one rule")
        super().__init__(self._summary())

    def _summary(self) -> str:
        if len(self.rules) == 1:
            return self.rules[0].detail
        return f"{len(self.rules)} rules were not satisfied"

    @property
    def codes(self) -> list[str]:
        return [rule.code for rule in self.rules]

    @classmethod
    def one(cls, code: str, detail: str, subject: str | None = None) -> RuleBroken:
        return cls([Rule(code, detail, subject)])
