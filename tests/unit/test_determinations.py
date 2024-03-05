"""What a set of determinations says about itself.

The distinction this class exists to keep is between a figure that was
determined and one that was not. A germination of zero means every seed in the
test was dead. No germination at all means nobody tested it. A buyer reading
the certificate can act on either, and cannot act on the two of them written
the same way.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from arc.certificates.model import Determinations
from arc.quantities import Percentage


class TestNothingDetermined:
    def test_an_empty_set_has_no_purity(self) -> None:
        assert Determinations().has_purity is False

    def test_and_no_germination(self) -> None:
        assert Determinations().has_germination is False

    def test_and_nothing_to_list(self) -> None:
        assert Determinations().determinations() == ()

    def test_every_field_starts_absent(self) -> None:
        empty = Determinations()

        assert empty.pure_seed is None
        assert empty.other_seed is None
        assert empty.inert_matter is None
        assert empty.germination_percent is None
        assert empty.germination_tested_on is None
        assert empty.moisture_percent is None
        assert empty.thousand_seed_weight_g is None


class TestAbsentIsNotZero:
    def test_a_germination_of_zero_was_determined(self) -> None:
        # Every seed dead is a result, and a bad one. It is not the same as
        # not having looked.
        dead = Determinations(germination_percent=0)

        assert dead.has_germination is True
        assert "germination" in dead.determinations()

    def test_a_purity_of_zero_percent_pure_seed_was_determined(self) -> None:
        nothing_pure = Determinations(pure_seed=Percentage("0.0"))

        assert nothing_pure.has_purity is True

    def test_no_germination_at_all_was_not(self) -> None:
        assert Determinations().has_germination is False

    def test_a_moisture_of_zero_counts_as_done(self) -> None:
        assert Determinations(moisture_percent=Decimal("0.0")).determinations() == ("moisture",)


class TestListingWhatWasDone:
    def test_purity_alone(self) -> None:
        results = Determinations(pure_seed=Percentage("98.4"))

        assert results.determinations() == ("purity",)

    def test_purity_and_germination(self) -> None:
        results = Determinations(
            pure_seed=Percentage("98.4"),
            germination_percent=96,
            germination_tested_on=date(2024, 9, 28),
        )

        assert results.determinations() == ("purity", "germination")

    def test_the_physical_determinations_come_after_the_others(self) -> None:
        results = Determinations(
            pure_seed=Percentage("98.4"),
            germination_percent=96,
            moisture_percent=Decimal("14.0"),
            thousand_seed_weight_g=Decimal("45.0"),
        )

        assert results.determinations() == (
            "purity",
            "germination",
            "moisture",
            "thousand seed weight",
        )

    def test_a_moisture_on_its_own_is_a_perfectly_good_job(self) -> None:
        # Merchants ask for one determination all the time, usually because
        # they are deciding whether the lot is dry enough to store.
        results = Determinations(moisture_percent=Decimal("14.0"))

        assert results.determinations() == ("moisture",)

    def test_the_date_a_germination_was_tested_is_not_a_determination(self) -> None:
        results = Determinations(germination_tested_on=date(2024, 9, 28))

        assert results.determinations() == ()


class TestTheseAreValues:
    def test_two_sets_with_the_same_figures_are_equal(self) -> None:
        assert Determinations(pure_seed=Percentage("98.4")) == Determinations(
            pure_seed=Percentage("98.4")
        )

    def test_and_two_with_different_ones_are_not(self) -> None:
        assert Determinations(pure_seed=Percentage("98.4")) != Determinations(
            pure_seed=Percentage("98.5")
        )

    def test_they_cannot_be_edited_after_the_fact(self) -> None:
        results = Determinations(pure_seed=Percentage("98.4"))

        try:
            results.pure_seed = Percentage("99.9")  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("a set of determinations should be frozen")
