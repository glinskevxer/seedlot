"""Holding the sample, and what is left of it.

Wheat throughout unless the point is that the figure follows the species. A
wheat submitted sample is a kilogram, its purity working sample is 120 g, and
its other seed working sample is ten times that, so a jar of a kilogram can
cover a search once and then very little else.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from arc.certificates.model import CertificateKind
from arc.retention.model import (
    UNCERTIFIED_RETENTION,
    Determination,
    DisposalReason,
    RetainedSample,
    retention_period,
)
from arc.retention.rules import (
    check_disposal,
    check_repeat,
    needed_for,
    possible_from,
)
from arc.species.model import Species

HELD_FROM = date(2024, 10, 2)
TODAY = date(2024, 11, 21)


def a_sample(
    *,
    remaining: str = "1000.0",
    kind: CertificateKind | None = CertificateKind.ORANGE_INTERNATIONAL,
    disposed_on: date | None = None,
    reason: DisposalReason | None = None,
) -> RetainedSample:
    return RetainedSample(
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        remaining_g=Decimal(remaining),
        held_from=HELD_FROM,
        certificate_kind=kind,
        disposed_on=disposed_on,
        disposal_reason=reason,
    )


def codes(rules) -> list[str]:
    return [rule.code for rule in rules]


class TestHowLongItIsHeld:
    def test_an_orange_certificate_is_backed_for_a_year(self) -> None:
        assert retention_period(CertificateKind.ORANGE_INTERNATIONAL) == timedelta(days=365)

    def test_a_green_report_for_half_of_one(self) -> None:
        assert retention_period(CertificateKind.GREEN_ANALYSIS) == timedelta(days=182)

    def test_a_sample_with_no_certificate_is_still_held(self) -> None:
        assert retention_period(None) == UNCERTIFIED_RETENTION

    def test_the_period_runs_from_the_certificate(self) -> None:
        assert a_sample().hold_until == date(2025, 10, 2)

    def test_days_left_counts_down(self) -> None:
        assert a_sample().days_left_on(date(2025, 10, 1)) == 1
        assert a_sample().days_left_on(date(2025, 10, 2)) == 0

    def test_and_goes_negative_once_it_is_past(self) -> None:
        assert a_sample().days_left_on(date(2025, 10, 5)) == -3

    def test_it_is_not_due_on_the_last_day(self) -> None:
        assert a_sample().is_due_for_disposal_on(date(2025, 10, 2)) is False

    def test_but_it_is_the_day_after(self) -> None:
        assert a_sample().is_due_for_disposal_on(date(2025, 10, 3)) is True

    def test_a_disposed_sample_is_never_due_again(self) -> None:
        gone = a_sample(disposed_on=date(2025, 10, 3), reason=DisposalReason.PERIOD_EXPIRED)

        assert gone.is_due_for_disposal_on(date(2026, 1, 1)) is False
        assert gone.is_held is False


class TestWhatTheJarWillAccept:
    def test_a_sample_cannot_hold_less_than_nothing(self) -> None:
        with pytest.raises(ValueError, match="less than nothing"):
            a_sample(remaining="-1")

    def test_a_disposal_has_to_say_why(self) -> None:
        with pytest.raises(ValueError, match="has to say why"):
            RetainedSample(
                lot_reference="L-2024-0041",
                species_name="Triticum aestivum",
                remaining_g=Decimal("1000.0"),
                held_from=HELD_FROM,
                disposed_on=date(2025, 1, 1),
            )

    def test_it_cannot_go_before_it_arrived(self) -> None:
        with pytest.raises(ValueError, match="before it was held"):
            a_sample(disposed_on=date(2024, 9, 1), reason=DisposalReason.SPOILED)


class TestDrawingFromTheJar:
    def test_a_draw_leaves_the_rest_behind(self) -> None:
        left = a_sample().draw(Decimal("120.0"))

        assert left.remaining_g == Decimal("880.0")

    def test_the_original_is_untouched(self) -> None:
        original = a_sample()
        original.draw(Decimal("120.0"))

        assert original.remaining_g == Decimal("1000.0")

    def test_the_hold_date_carries_across(self) -> None:
        assert a_sample().draw(Decimal("120.0")).hold_until == date(2025, 10, 2)

    def test_drawing_more_than_is_there_is_refused(self) -> None:
        with pytest.raises(ValueError, match="holding 1000.0 g"):
            a_sample().draw(Decimal("1200.0"))

    def test_drawing_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a draw"):
            a_sample().draw(Decimal("0"))

    def test_the_jar_can_be_emptied_exactly(self) -> None:
        assert a_sample().draw(Decimal("1000.0")).remaining_g == Decimal("0.0")


class TestWhatEachDeterminationCosts:
    def test_a_purity_takes_its_working_sample(self, wheat: Species) -> None:
        assert needed_for(Determination.PURITY, wheat) == Decimal("120")

    def test_a_search_takes_ten_of_them(self, wheat: Species) -> None:
        assert needed_for(Determination.OTHER_SEED, wheat) == Decimal("1200")

    def test_a_germination_is_four_hundred_seeds(self, wheat: Species) -> None:
        assert needed_for(Determination.GERMINATION, wheat) == Decimal("20.0")

    def test_a_seed_weight_is_twice_that(self, wheat: Species) -> None:
        assert needed_for(Determination.THOUSAND_SEED_WEIGHT, wheat) == Decimal("40.0")

    def test_moisture_is_the_same_for_everything(self, wheat, ryegrass) -> None:
        assert needed_for(Determination.MOISTURE, wheat) == Decimal("25.0")
        assert needed_for(Determination.MOISTURE, ryegrass) == Decimal("25.0")

    def test_a_grass_germination_takes_far_less_than_a_cereal_one(
        self, wheat: Species, ryegrass: Species
    ) -> None:
        assert needed_for(Determination.GERMINATION, ryegrass) < needed_for(
            Determination.GERMINATION, wheat
        )


class TestWhatIsStillPossible:
    def test_a_full_jar_could_cover_anything(self, wheat: Species) -> None:
        possible = possible_from(a_sample(remaining="2000.0"), wheat)

        assert set(possible) == set(Determination)

    def test_a_kilogram_cannot_cover_the_search(self, wheat: Species) -> None:
        possible = possible_from(a_sample(), wheat)

        assert Determination.OTHER_SEED not in possible
        assert Determination.PURITY in possible

    def test_a_nearly_empty_jar_covers_nothing(self, wheat: Species) -> None:
        assert possible_from(a_sample(remaining="5.0"), wheat) == ()

    def test_a_disposed_jar_covers_nothing_either(self, wheat: Species) -> None:
        gone = a_sample(disposed_on=date(2025, 10, 3), reason=DisposalReason.PERIOD_EXPIRED)

        assert possible_from(gone, wheat) == ()

    def test_exactly_enough_counts_as_enough(self, wheat: Species) -> None:
        assert Determination.PURITY in possible_from(a_sample(remaining="120"), wheat)


class TestTheOrderTheRepeatsAreDoneIn:
    def test_a_purity_then_a_germination_both_fit(self, wheat: Species) -> None:
        jar = a_sample(remaining="200.0")

        assert check_repeat(jar, Determination.PURITY, wheat, on=TODAY) == []
        after = jar.draw(needed_for(Determination.PURITY, wheat))
        assert check_repeat(after, Determination.GERMINATION, wheat, on=TODAY) == []

    def test_but_the_search_first_leaves_room_for_nothing(self, wheat: Species) -> None:
        # 1300 g covers the search on its own and covers a purity on its own.
        # It does not cover both, and which one becomes impossible depends
        # entirely on which one was drawn first.
        jar = a_sample(remaining="1300.0")

        assert check_repeat(jar, Determination.OTHER_SEED, wheat, on=TODAY) == []
        after = jar.draw(needed_for(Determination.OTHER_SEED, wheat))

        assert codes(check_repeat(after, Determination.PURITY, wheat, on=TODAY)) == [
            "SAMPLE_TOO_SMALL_TO_REPEAT"
        ]

    def test_and_the_other_way_round_leaves_the_search_impossible(self, wheat: Species) -> None:
        jar = a_sample(remaining="1300.0")
        after = jar.draw(needed_for(Determination.PURITY, wheat))

        assert codes(check_repeat(after, Determination.OTHER_SEED, wheat, on=TODAY)) == [
            "SAMPLE_TOO_SMALL_TO_REPEAT"
        ]


class TestRepeatingATest:
    def test_a_full_jar_inside_its_period_is_fine(self, wheat: Species) -> None:
        assert check_repeat(a_sample(), Determination.PURITY, wheat, on=TODAY) == []

    def test_a_short_jar_says_how_short(self, wheat: Species) -> None:
        broken = check_repeat(a_sample(remaining="100"), Determination.PURITY, wheat, on=TODAY)

        assert codes(broken) == ["SAMPLE_TOO_SMALL_TO_REPEAT"]
        assert "20 g short" in broken[0].detail

    def test_a_disposed_jar_stops_everything_else_being_checked(self, wheat: Species) -> None:
        gone = a_sample(
            remaining="0", disposed_on=date(2025, 1, 5), reason=DisposalReason.SPOILED
        )

        broken = check_repeat(gone, Determination.PURITY, wheat, on=TODAY)

        assert codes(broken) == ["SAMPLE_NOT_HELD"]
        assert "spoiled in store" in broken[0].detail

    def test_a_jar_past_its_period_is_flagged_but_not_the_end_of_it(
        self, wheat: Species
    ) -> None:
        # The seed is still there and can still be tested. What it can no
        # longer be is the sample the certificate is backed by.
        broken = check_repeat(a_sample(), Determination.PURITY, wheat, on=date(2025, 11, 1))

        assert codes(broken) == ["SAMPLE_PAST_ITS_PERIOD"]

    def test_both_problems_come_back_together(self, wheat: Species) -> None:
        broken = check_repeat(
            a_sample(remaining="10"), Determination.PURITY, wheat, on=date(2025, 11, 1)
        )

        assert set(codes(broken)) == {
            "SAMPLE_TOO_SMALL_TO_REPEAT",
            "SAMPLE_PAST_ITS_PERIOD",
        }


class TestThrowingItOut:
    def test_a_sample_inside_its_period_may_not_go(self) -> None:
        broken = check_disposal(a_sample(), on=TODAY)

        assert codes(broken) == ["SAMPLE_STILL_IN_ITS_PERIOD"]
        assert "315 days away" in broken[0].detail

    def test_one_past_its_period_may(self) -> None:
        assert check_disposal(a_sample(), on=date(2025, 10, 3)) == []

    def test_not_on_the_last_day_of_it(self) -> None:
        assert codes(check_disposal(a_sample(), on=date(2025, 10, 2))) == [
            "SAMPLE_STILL_IN_ITS_PERIOD"
        ]

    def test_one_that_has_already_gone_cannot_go_again(self) -> None:
        gone = a_sample(disposed_on=date(2025, 10, 3), reason=DisposalReason.PERIOD_EXPIRED)

        assert codes(check_disposal(gone, on=date(2025, 11, 1))) == ["SAMPLE_ALREADY_DISPOSED"]

    def test_an_uncertified_sample_comes_free_much_sooner(self) -> None:
        uncertified = a_sample(kind=None)

        assert uncertified.hold_until == HELD_FROM + UNCERTIFIED_RETENTION
        assert check_disposal(uncertified, on=date(2025, 3, 1)) == []


class TestTheLineForTheStoreList:
    def test_a_held_sample_says_how_long_is_left(self) -> None:
        assert a_sample().describe(TODAY) == "L-2024-0041 1000.0 g, 315 days left"

    def test_an_overdue_one_says_how_far_past_it_is(self) -> None:
        assert a_sample().describe(date(2025, 10, 5)) == (
            "L-2024-0041 1000.0 g, 3 days overdue"
        )

    def test_a_disposed_one_says_when_and_why(self) -> None:
        gone = a_sample(
            disposed_on=date(2025, 10, 3), reason=DisposalReason.RETURNED_TO_MERCHANT
        )

        assert gone.describe(TODAY) == (
            "L-2024-0041 disposed 2025-10-03, returned to the merchant"
        )
