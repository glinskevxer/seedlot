"""The sample store, round tripped.

The one table in the database that is updated rather than appended to, which is
why the draws sit beside it. Several of these tests check the two stay in step,
because the day they do not is the day the store list says there is seed in a
jar that is empty.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.errors import NotFound
from arc.retention.model import Determination, DisposalReason, RetainedSample
from arc.storage.lots import LotRepository
from arc.storage.retention import RetentionRepository

BOOKED = date(2024, 11, 4)
HELD_FROM = date(2024, 12, 2)
LOT = "L-2024-0041"


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield connection
    connection.close()


@pytest.fixture
def store(db) -> RetentionRepository:
    return RetentionRepository(db)


def a_sample(
    *,
    remaining: str = "1000.0",
    kind: CertificateKind | None = CertificateKind.ORANGE_INTERNATIONAL,
) -> RetainedSample:
    return RetainedSample(
        lot_reference=LOT,
        species_name="Triticum aestivum",
        remaining_g=Decimal(remaining),
        held_from=HELD_FROM,
        certificate_kind=kind,
    )


class TestPuttingASampleAway:
    def test_it_comes_back_as_it_went_in(self, store) -> None:
        store.place(a_sample())

        found = store.require(LOT)

        assert found.remaining_g == Decimal("1000.0")
        assert found.held_from == HELD_FROM
        assert found.certificate_kind is CertificateKind.ORANGE_INTERNATIONAL
        assert found.is_held is True

    def test_the_weight_keeps_the_places_it_was_weighed_to(self, store) -> None:
        store.place(a_sample(remaining="998.50"))

        assert str(store.require(LOT).remaining_g) == "998.50"

    def test_a_sample_with_no_certificate_behind_it(self, store) -> None:
        store.place(a_sample(kind=None))

        found = store.require(LOT)

        assert found.certificate_kind is None
        assert found.hold_until == date(2025, 3, 2)

    def test_a_lot_with_nothing_in_the_store(self, store) -> None:
        assert store.find(LOT) is None

    def test_and_asking_for_it_by_name_refuses(self, store) -> None:
        with pytest.raises(NotFound, match="retained sample"):
            store.require(LOT)

    def test_placing_it_twice_resets_the_period_to_the_later_claim(self, store) -> None:
        store.place(a_sample(kind=CertificateKind.GREEN_ANALYSIS))
        store.place(a_sample(kind=CertificateKind.ORANGE_INTERNATIONAL))

        assert store.require(LOT).hold_until == date(2025, 12, 2)

    def test_a_sample_for_a_lot_nobody_booked_in_is_refused(self, store) -> None:
        stray = RetainedSample(
            lot_reference="L-2024-9999",
            species_name="Triticum aestivum",
            remaining_g=Decimal("1000.0"),
            held_from=HELD_FROM,
        )

        with pytest.raises(sqlite3.IntegrityError):
            store.place(stray)


class TestDrawingFromTheStore:
    def test_the_remaining_weight_comes_down(self, store) -> None:
        store.place(a_sample())

        left = store.draw(
            LOT,
            Determination.PURITY,
            Decimal("120.0"),
            on=date(2024, 12, 9),
            analyst="J. Whitfield",
        )

        assert left.remaining_g == Decimal("880.0")
        assert store.require(LOT).remaining_g == Decimal("880.0")

    def test_the_draw_is_written_down(self, store) -> None:
        store.place(a_sample())
        store.draw(
            LOT,
            Determination.PURITY,
            Decimal("120.0"),
            on=date(2024, 12, 9),
            analyst="J. Whitfield",
        )

        draws = store.draws_for(LOT)

        assert len(draws) == 1
        assert draws[0].determination is Determination.PURITY
        assert draws[0].weight_g == Decimal("120.0")
        assert draws[0].analyst == "J. Whitfield"

    def test_the_draws_add_up_to_what_is_gone(self, store) -> None:
        store.place(a_sample())
        store.draw(
            LOT, Determination.PURITY, Decimal("120.0"), on=date(2024, 12, 9), analyst="J. W."
        )
        store.draw(
            LOT,
            Determination.GERMINATION,
            Decimal("20.0"),
            on=date(2024, 12, 10),
            analyst="J. W.",
        )

        drawn = sum(draw.weight_g for draw in store.draws_for(LOT))

        assert drawn == Decimal("140.0")
        assert store.require(LOT).remaining_g == Decimal("1000.0") - drawn

    def test_drawing_more_than_is_there_is_refused(self, store) -> None:
        store.place(a_sample(remaining="100.0"))

        with pytest.raises(ValueError, match="holding 100.0 g"):
            store.draw(
                LOT,
                Determination.PURITY,
                Decimal("120.0"),
                on=date(2024, 12, 9),
                analyst="J. W.",
            )

    def test_and_leaves_neither_the_weight_nor_the_log_touched(self, store) -> None:
        store.place(a_sample(remaining="100.0"))

        with pytest.raises(ValueError):
            store.draw(
                LOT,
                Determination.PURITY,
                Decimal("120.0"),
                on=date(2024, 12, 9),
                analyst="J. W.",
            )

        assert store.require(LOT).remaining_g == Decimal("100.0")
        assert store.draws_for(LOT) == ()

    def test_a_draw_against_a_sample_that_is_not_there(self, store) -> None:
        with pytest.raises(NotFound):
            store.draw(
                LOT,
                Determination.PURITY,
                Decimal("120.0"),
                on=date(2024, 12, 9),
                analyst="J. W.",
            )


class TestThrowingItOut:
    def test_a_disposed_sample_is_no_longer_held(self, store) -> None:
        store.place(a_sample())

        gone = store.dispose(LOT, on=date(2025, 12, 3), reason=DisposalReason.PERIOD_EXPIRED)

        assert gone.is_held is False
        assert gone.disposed_on == date(2025, 12, 3)
        assert gone.disposal_reason is DisposalReason.PERIOD_EXPIRED

    def test_the_row_stays_so_the_history_does(self, store) -> None:
        store.place(a_sample())
        store.dispose(LOT, on=date(2025, 12, 3), reason=DisposalReason.SPOILED)

        assert store.find(LOT) is not None

    def test_disposing_of_it_twice_is_refused(self, store) -> None:
        store.place(a_sample())
        store.dispose(LOT, on=date(2025, 12, 3), reason=DisposalReason.SPOILED)

        with pytest.raises(ValueError, match="already disposed"):
            store.dispose(LOT, on=date(2025, 12, 4), reason=DisposalReason.SPOILED)

    def test_a_disposal_without_a_reason_cannot_be_written(self, db, store) -> None:
        store.place(a_sample())

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "update retained_sample set disposed_on = '2025-12-03' "
                "where lot_reference = ?",
                (LOT,),
            )


class TestTheStoreList:
    def test_everything_held_comes_back_oldest_first(self, db, store) -> None:
        lots = LotRepository(db)
        second = make_lot(serial=42)
        lots.save(second, booked_in_on=BOOKED)

        store.place(a_sample())
        store.place(
            RetainedSample(
                lot_reference="L-2024-0042",
                species_name="Triticum aestivum",
                remaining_g=Decimal("900.0"),
                held_from=date(2024, 11, 20),
            )
        )

        assert [sample.lot_reference for sample in store.held()] == [
            "L-2024-0042",
            LOT,
        ]

    def test_a_disposed_sample_is_off_the_list(self, store) -> None:
        store.place(a_sample())
        store.dispose(LOT, on=date(2025, 12, 3), reason=DisposalReason.PERIOD_EXPIRED)

        assert store.held() == ()

    def test_nothing_is_due_while_the_period_runs(self, store) -> None:
        store.place(a_sample())

        assert store.due_for_disposal(date(2025, 6, 1)) == ()

    def test_and_it_is_due_the_day_after_the_period_ends(self, store) -> None:
        store.place(a_sample())

        assert store.due_for_disposal(date(2025, 12, 2)) == ()
        assert len(store.due_for_disposal(date(2025, 12, 3))) == 1

    def test_the_period_follows_the_certificate_that_was_issued(self, db, store) -> None:
        # A green report is held half as long, so on the same day one sample is
        # due and the other is not.
        lots = LotRepository(db)
        lots.save(make_lot(serial=42), booked_in_on=BOOKED)

        store.place(a_sample())
        store.place(
            RetainedSample(
                lot_reference="L-2024-0042",
                species_name="Triticum aestivum",
                remaining_g=Decimal("900.0"),
                held_from=HELD_FROM,
                certificate_kind=CertificateKind.GREEN_ANALYSIS,
            )
        )

        due = store.due_for_disposal(date(2025, 7, 1))

        assert [sample.lot_reference for sample in due] == ["L-2024-0042"]
