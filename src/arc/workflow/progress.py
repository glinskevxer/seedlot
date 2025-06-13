"""Moving a lot along as the work is done.

The status machine is strict on purpose: a lot goes booked in, sampled, in
test, reported, closed, and it cannot skip. What was missing is anything that
actually walked it. Every lot booked in from the console stayed booked in for
ever, which meant the Monday morning list never got shorter and a lot certified
in March was still on it in June.

Nobody is going to type a status change. The status is a consequence of the
work: the sample is on the bench because somebody is recording a determination
off it, and the lot is reported because a certificate went out. So both
transitions happen where those things happen.
"""

from __future__ import annotations

from datetime import date

from arc.lots.model import LotStatus, SeedLot
from arc.storage.lots import LotRepository

__all__ = ["begin_testing", "mark_reported"]


def begin_testing(lot: SeedLot, lots: LotRepository, *, on: date) -> SeedLot:
    """Walks a lot up to in test, from wherever it is.

    Recording a determination is the evidence. A lot still marked booked in
    with a purity analysis against it is a lot whose paperwork disagrees with
    its own results.

    Doing nothing to a lot that is already reported is deliberate rather than
    an oversight. A repeat test on a certified lot happens, and it does not
    put the lot back into the queue.
    """
    if not lot.status.is_open:
        return lot

    for step in (LotStatus.SAMPLED, LotStatus.IN_TEST):
        if lot.status is step:
            continue
        if lot.status.can_move_to(step):
            lot.move_to(step)

    lots.save(lot, booked_in_on=on)
    return lot


def mark_reported(lot: SeedLot, lots: LotRepository, *, on: date) -> SeedLot:
    """Walks a lot to reported once a certificate has gone out.

    Through the intermediate states rather than jumping, because the machine
    refuses a jump and a lot that was certified without ever being marked as
    on the bench is still a lot that was certified.
    """
    if not lot.status.is_open:
        return lot

    for step in (LotStatus.SAMPLED, LotStatus.IN_TEST, LotStatus.REPORTED):
        if lot.status.can_move_to(step):
            lot.move_to(step)

    lots.save(lot, booked_in_on=on)
    return lot
