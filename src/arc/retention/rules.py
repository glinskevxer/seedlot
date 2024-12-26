"""What can still be done with what is left of the sample.

Two things decide it and they pull in different directions. The calendar says
the station has to be able to produce the sample until a certain day. The
balance says how much of it is actually there, and every repeat test takes some
away.

The part worth reading twice is that the order matters. A retained sample big
enough for a purity and a germination is not big enough for both if the other
seed search is done first, because that one alone takes ten purity working
samples. So the question is never "can this test be repeated". It is "can this
test be repeated given what has already come out of the jar", and a station
that answers the first question will lose the ability to answer a dispute
without noticing it did.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from arc.errors import Rule
from arc.retention.model import Determination, RetainedSample
from arc.species.model import SeedClass, Species

__all__ = [
    "GERMINATION_SEEDS",
    "MOISTURE_SAMPLE_G",
    "FOUR_HUNDRED_SEEDS_G",
    "needed_for",
    "possible_from",
    "check_repeat",
    "check_disposal",
]

#: A germination is four hundred seeds, whatever the species.
GERMINATION_SEEDS = 400

#: Moisture takes two ten gram sub samples and loses some to the grinder.
MOISTURE_SAMPLE_G = Decimal("25.0")

#: Roughly what four hundred seeds of each kind of seed weigh. Rough is the
#: right word: it is a store keeping figure used to decide whether the jar can
#: still answer a question, and the actual working sample is weighed at the
#: bench when the time comes.
FOUR_HUNDRED_SEEDS_G: dict[SeedClass, Decimal] = {
    SeedClass.CEREAL: Decimal("20.0"),
    SeedClass.LARGE_LEGUME: Decimal("150.0"),
    SeedClass.SMALL_LEGUME: Decimal("2.0"),
    SeedClass.GRASS: Decimal("1.0"),
    SeedClass.BRASSICA: Decimal("2.0"),
    SeedClass.VEGETABLE: Decimal("5.0"),
    SeedClass.BEET: Decimal("10.0"),
    SeedClass.OIL_AND_FIBRE: Decimal("3.0"),
}


def needed_for(determination: Determination, species: Species) -> Decimal:
    """How much seed one repeat of this determination takes out of the jar."""
    four_hundred = FOUR_HUNDRED_SEEDS_G[species.seed_class]

    if determination is Determination.PURITY:
        return species.purity_working_sample_g
    if determination is Determination.OTHER_SEED:
        return species.other_seed_working_sample_g
    if determination is Determination.GERMINATION:
        return four_hundred
    if determination is Determination.THOUSAND_SEED_WEIGHT:
        # Eight replicates of a hundred, which is twice a germination.
        return four_hundred * 2
    return MOISTURE_SAMPLE_G


def possible_from(sample: RetainedSample, species: Species) -> tuple[Determination, ...]:
    """Every determination the jar could still cover, one at a time.

    One at a time is the whole caveat. Two determinations both appearing here
    does not mean both can be done, and check_repeat is what answers that as
    each one is actually drawn.
    """
    if not sample.is_held:
        return ()

    return tuple(
        determination
        for determination in Determination
        if needed_for(determination, species) <= sample.remaining_g
    )


def check_repeat(
    sample: RetainedSample,
    determination: Determination,
    species: Species,
    *,
    on: date,
) -> list[Rule]:
    """Whether this repeat may be drawn from this jar today."""
    broken: list[Rule] = []
    subject = sample.lot_reference

    if not sample.is_held:
        reason = sample.disposal_reason.value if sample.disposal_reason else "unstated"
        broken.append(
            Rule(
                "SAMPLE_NOT_HELD",
                f"the retained sample went on {sample.disposed_on} ({reason}), "
                "so there is nothing to repeat the test on",
                subject,
            )
        )
        return broken

    needed = needed_for(determination, species)
    if sample.remaining_g < needed:
        short_by = needed - sample.remaining_g
        broken.append(
            Rule(
                "SAMPLE_TOO_SMALL_TO_REPEAT",
                f"a {determination.value} on {species.common_name} takes "
                f"{needed} g and the jar holds {sample.remaining_g} g, "
                f"{short_by} g short",
                subject,
            )
        )

    if sample.is_due_for_disposal_on(on):
        # Still there, and past the day anybody was entitled to expect it.
        # Testing it is allowed; reporting it as though the sample were
        # covered by the retention period is not.
        broken.append(
            Rule(
                "SAMPLE_PAST_ITS_PERIOD",
                f"the retention period ran out on {sample.hold_until}, so this "
                "sample is no longer the one the certificate is backed by",
                subject,
            )
        )

    return broken


def check_disposal(
    sample: RetainedSample,
    *,
    on: date,
) -> list[Rule]:
    """Whether the store may throw this jar out today."""
    broken: list[Rule] = []
    subject = sample.lot_reference

    if not sample.is_held:
        broken.append(
            Rule(
                "SAMPLE_ALREADY_DISPOSED",
                f"this sample went on {sample.disposed_on}",
                subject,
            )
        )
        return broken

    if not sample.is_due_for_disposal_on(on):
        days = sample.days_left_on(on)
        broken.append(
            Rule(
                "SAMPLE_STILL_IN_ITS_PERIOD",
                f"the certificate is backed by this sample until "
                f"{sample.hold_until}, {days} days away",
                subject,
            )
        )

    return broken
