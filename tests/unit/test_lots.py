"""Lot references, how a lot is put up, and whether it may be tested."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.conftest import make_lot

from arc.lots import (
    ContainerKind,
    LotReference,
    LotStatus,
    check_lot,
    must_be_sampled_in_stream,
    over_maximum_by,
    sublots_needed,
)


class TestLotReference:
    def test_it_prints_the_way_the_label_is_written(self) -> None:
        assert str(LotReference(2024, 41)) == "L-2024-0041"

    def test_it_parses_what_it_prints(self) -> None:
        assert LotReference.parse("L-2024-0041") == LotReference(2024, 41)

    def test_case_and_spaces_do_not_matter(self) -> None:
        assert LotReference.parse("  l-2024-0041 ") == LotReference(2024, 41)

    def test_anything_that_is_not_a_reference_is_refused(self) -> None:
        for bad in ("2024-0041", "L-24-0041", "L-2024-41", "L-2024-00041", ""):
            with pytest.raises(ValueError, match="not a lot reference"):
                LotReference.parse(bad)

    def test_a_year_the_station_never_worked_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a year"):
            LotReference(1999, 41)

    def test_a_serial_outside_the_book_is_refused(self) -> None:
        with pytest.raises(ValueError, match="1 to 9999"):
            LotReference(2024, 0)

    def test_references_sort_by_year_then_serial(self) -> None:
        assert sorted(
            [LotReference(2024, 41), LotReference(2023, 900), LotReference(2024, 7)]
        ) == [LotReference(2023, 900), LotReference(2024, 7), LotReference(2024, 41)]


class TestHowTheLotIsPutUp:
    def test_a_bulk_lot_has_no_containers_to_count(self) -> None:
        lot = make_lot(container_kind=ContainerKind.BULK, container_count=0)

        assert lot.average_container_kg is None

    def test_a_containerised_lot_averages_out_its_containers(self) -> None:
        lot = make_lot(weight_kg="24000", container_count=480)

        assert lot.average_container_kg == Decimal(50)

    def test_a_bulk_lot_that_claims_containers_is_a_typo(self) -> None:
        with pytest.raises(ValueError, match="no containers to count"):
            make_lot(container_kind=ContainerKind.BULK, container_count=12)

    def test_a_containerised_lot_with_no_containers_is_a_typo(self) -> None:
        with pytest.raises(ValueError, match="at least one container"):
            make_lot(container_count=0)

    def test_an_empty_lot_is_not_a_lot(self) -> None:
        with pytest.raises(ValueError, match="no seed in it"):
            make_lot(weight_kg="0")

    def test_the_origin_is_a_country_code(self) -> None:
        from datetime import date

        from arc.lots.model import SeedLot

        with pytest.raises(ValueError, match="two letter code"):
            SeedLot(
                reference=LotReference(2024, 1),
                species_name="Triticum aestivum",
                declared_weight_kg=Decimal(100),
                container_kind=ContainerKind.BULK,
                container_count=0,
                merchant="Ravenscar Grain",
                sealed_on=date(2024, 9, 1),
                origin_country="GBR",
            )


class TestSamplingRoute:
    def test_ordinary_bags_can_be_speared_where_they_stand(self) -> None:
        assert not must_be_sampled_in_stream(make_lot(weight_kg="24000", container_count=480))

    def test_bulk_never_can(self) -> None:
        assert must_be_sampled_in_stream(
            make_lot(container_kind=ContainerKind.BULK, container_count=0)
        )

    def test_big_bags_never_can_either(self) -> None:
        assert must_be_sampled_in_stream(
            make_lot(
                container_kind=ContainerKind.BIG_BAG,
                weight_kg="24000",
                container_count=24,
            )
        )

    def test_bags_too_heavy_to_reach_the_middle_of_are_treated_as_bulk(self) -> None:
        # Called bags on the paperwork, half a tonne each in the warehouse.
        assert must_be_sampled_in_stream(make_lot(weight_kg="24000", container_count=48))


class TestMaximumLotWeight:
    def test_a_lot_inside_the_maximum_is_not_over_it(self, wheat) -> None:
        assert over_maximum_by(make_lot(weight_kg="24000"), wheat) == 0
        assert sublots_needed(make_lot(weight_kg="24000"), wheat) == 1
        assert check_lot(make_lot(weight_kg="24000"), wheat) == []

    def test_exactly_on_the_maximum_is_inside_it(self, wheat) -> None:
        assert check_lot(make_lot(weight_kg="30000"), wheat) == []

    def test_four_percent_over_is_inside_the_allowance(self, wheat) -> None:
        lot = make_lot(weight_kg="31200")

        assert over_maximum_by(lot, wheat) == Decimal("0.04")
        assert sublots_needed(lot, wheat) == 1
        assert check_lot(lot, wheat) == []

    def test_exactly_five_percent_over_is_still_inside_it(self, wheat) -> None:
        lot = make_lot(weight_kg="31500")

        assert over_maximum_by(lot, wheat) == Decimal("0.05")
        assert check_lot(lot, wheat) == []

    def test_six_percent_over_has_to_be_split(self, wheat) -> None:
        lot = make_lot(weight_kg="31800")

        broken = check_lot(lot, wheat)

        assert [rule.code for rule in broken] == ["LOT_OVER_MAXIMUM"]
        assert "2 sublots" in broken[0].detail

    def test_the_number_of_sublots_rounds_up(self, wheat) -> None:
        assert sublots_needed(make_lot(weight_kg="60000"), wheat) == 2
        assert sublots_needed(make_lot(weight_kg="60001"), wheat) == 3
        assert sublots_needed(make_lot(weight_kg="90000"), wheat) == 3

    def test_the_maximum_is_the_species_own_one(self, ryegrass) -> None:
        # Ten tonnes for grass, where wheat would be fine at thirty.
        lot = make_lot(species_name="Lolium perenne", weight_kg="24000", container_count=960)

        broken = check_lot(lot, ryegrass)

        assert [rule.code for rule in broken] == ["LOT_OVER_MAXIMUM"]
        assert "10000 kg maximum" in broken[0].detail


class TestOtherChecksAtBookingIn:
    def test_bags_too_heavy_to_spear_are_reported(self, wheat) -> None:
        broken = check_lot(make_lot(weight_kg="24000", container_count=48), wheat)

        assert [rule.code for rule in broken] == ["BAGS_TOO_HEAVY"]
        assert "500.0 kg" in broken[0].detail

    def test_an_implausible_container_count_is_reported(self, wheat) -> None:
        broken = check_lot(make_lot(weight_kg="100", container_count=480), wheat)

        assert "CONTAINER_COUNT_IMPLAUSIBLE" in [rule.code for rule in broken]

    def test_several_problems_come_back_together(self, ryegrass) -> None:
        lot = make_lot(species_name="Lolium perenne", weight_kg="24000", container_count=48)

        assert [rule.code for rule in check_lot(lot, ryegrass)] == [
            "LOT_OVER_MAXIMUM",
            "BAGS_TOO_HEAVY",
        ]


class TestLotLife:
    def test_a_lot_walks_through_its_states_in_order(self) -> None:
        lot = make_lot()

        for nxt in (LotStatus.SAMPLED, LotStatus.IN_TEST, LotStatus.REPORTED):
            lot.move_to(nxt)

        assert lot.status is LotStatus.REPORTED
        assert not lot.status.is_open

    def test_it_cannot_skip_a_step(self) -> None:
        lot = make_lot()

        with pytest.raises(ValueError, match="cannot go from booked in to in test"):
            lot.move_to(LotStatus.IN_TEST)

    def test_it_can_be_closed_from_anywhere_but_never_reopened(self) -> None:
        lot = make_lot()
        lot.move_to(LotStatus.CLOSED)

        with pytest.raises(ValueError, match="cannot go from closed"):
            lot.move_to(LotStatus.SAMPLED)

    def test_a_sublot_knows_what_it_came_out_of(self) -> None:
        parent = LotReference(2024, 41)
        sublot = make_lot(serial=42)
        sublot.sublot_of = parent

        assert sublot.is_sublot
        assert not make_lot().is_sublot

    def test_a_lot_prints_the_line_the_worksheet_carries(self) -> None:
        assert str(make_lot()) == "L-2024-0041 Triticum aestivum 24000 kg"
