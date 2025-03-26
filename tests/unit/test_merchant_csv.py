"""A merchant's spreadsheet, read the way merchants send them.

Every bad file in here is one somebody actually sends: a date written the way
the paperwork writes it, a species under a name the station does not test, a
lot reference with a letter missing, and the same lot listed twice because the
merchant appended to last week's file.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from arc.importing.merchant_csv import COLUMNS, parse
from arc.lots.model import ContainerKind

HEADER = ",".join(COLUMNS)
GOOD = "L-2024-0041,wheat,24000,bag,480,2024-09-12,GB"
MERCHANT = "Ravenscar Grain"


def a_file(*rows: str, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


class TestAFileThatIsFine:
    def test_one_row_becomes_one_lot(self) -> None:
        read = parse(a_file(GOOD), MERCHANT)

        assert read.is_clean
        assert len(read.lots) == 1

    def test_every_field_comes_across(self) -> None:
        lot = parse(a_file(GOOD), MERCHANT).lots[0]

        assert str(lot.reference) == "L-2024-0041"
        assert lot.species_name == "Triticum aestivum"
        assert lot.declared_weight_kg == Decimal("24000")
        assert lot.container_kind is ContainerKind.BAG
        assert lot.container_count == 480
        assert lot.sealed_on == date(2024, 9, 12)
        assert lot.origin_country == "GB"

    def test_the_merchant_comes_from_outside_the_file(self) -> None:
        # A row cannot name a different merchant, because a typo would then
        # book seed in against somebody else's account.
        lot = parse(a_file(GOOD), "Scarborough Seeds").lots[0]

        assert lot.merchant == "Scarborough Seeds"

    def test_a_common_name_is_turned_into_the_botanical_one(self) -> None:
        row = "L-2024-0042,bread wheat,24000,bag,480,2024-09-12,GB"

        assert parse(a_file(row), MERCHANT).lots[0].species_name == "Triticum aestivum"

    def test_the_origin_is_upper_cased(self) -> None:
        row = "L-2024-0042,wheat,24000,bag,480,2024-09-12,gb"

        assert parse(a_file(row), MERCHANT).lots[0].origin_country == "GB"

    def test_spaces_around_the_values_are_ignored(self) -> None:
        row = "  L-2024-0041 , wheat , 24000 , bag , 480 , 2024-09-12 , GB "

        assert parse(a_file(row), MERCHANT).is_clean

    def test_columns_the_station_did_not_ask_for_are_ignored(self) -> None:
        # Merchants send their own stock codes and there is no arguing them
        # out of it.
        header = HEADER + ",their reference"
        row = GOOD + ",STK-99201"

        assert parse(a_file(row, header=header), MERCHANT).is_clean

    def test_the_summary_says_what_happened(self) -> None:
        assert parse(a_file(GOOD), MERCHANT).summary() == "1 lots, no problems"


class TestManyRows:
    def test_they_all_come_through(self) -> None:
        rows = [
            GOOD,
            "L-2024-0042,barley,20000,bag,400,2024-09-13,GB",
            "L-2024-0043,perennial ryegrass,8000,bag,320,2024-09-14,GB",
        ]

        read = parse(a_file(*rows), MERCHANT)

        assert len(read.lots) == 3
        assert read.rows_read == 3

    def test_one_bad_row_does_not_stop_the_others(self) -> None:
        rows = [
            GOOD,
            "L-nonsense,wheat,24000,bag,480,2024-09-12,GB",
            "L-2024-0043,barley,20000,bag,400,2024-09-13,GB",
        ]

        read = parse(a_file(*rows), MERCHANT)

        assert len(read.lots) == 2
        assert len(read.problems) == 1

    def test_the_problem_carries_the_row_number_the_merchant_sees(self) -> None:
        # Their spreadsheet counts the header as row one, so the first row of
        # data is row two.
        rows = [GOOD, "L-nonsense,wheat,24000,bag,480,2024-09-12,GB"]

        problem = parse(a_file(*rows), MERCHANT).problems[0]

        assert problem.line == 3

    def test_the_same_lot_twice_is_caught(self) -> None:
        read = parse(a_file(GOOD, GOOD), MERCHANT)

        assert len(read.lots) == 1
        assert "already on the list" in read.problems[0].detail

    def test_the_summary_counts_both_sides(self) -> None:
        read = parse(a_file(GOOD, "rubbish,,,,,,"), MERCHANT)

        assert read.summary() == "1 lots, 1 rows to fix"


class TestFilesThatAreNotFilesYet:
    def test_an_empty_file(self) -> None:
        read = parse("", MERCHANT)

        assert read.lots == ()
        assert "empty" in read.problems[0].detail

    def test_a_file_with_only_a_header(self) -> None:
        read = parse(a_file(), MERCHANT)

        assert read.lots == ()
        assert read.problems == ()

    def test_a_file_missing_a_column(self) -> None:
        header = ",".join(name for name in COLUMNS if name != "origin")
        read = parse(
            a_file("L-2024-0041,wheat,24000,bag,480,2024-09-12", header=header), MERCHANT
        )

        assert "origin" in read.problems[0].detail

    def test_and_it_says_all_of_them_at_once(self) -> None:
        header = "lot,species"
        read = parse(a_file("L-2024-0041,wheat", header=header), MERCHANT)

        detail = read.problems[0].detail

        assert "weight kg" in detail
        assert "origin" in detail


class TestTheRowsMerchantsActuallyGetWrong:
    def problem(self, row: str) -> str:
        return parse(a_file(row), MERCHANT).problems[0].detail

    def test_a_lot_reference_in_the_wrong_shape(self) -> None:
        assert "lot reference" in self.problem("2024/41,wheat,24000,bag,480,2024-09-12,GB")

    def test_a_species_the_station_does_not_test(self) -> None:
        assert "does not test" in self.problem("L-2024-0041,quinoa,24000,bag,480,2024-09-12,GB")

    def test_a_weight_with_a_unit_typed_into_it(self) -> None:
        assert "not a number" in self.problem("L-2024-0041,wheat,24000kg,bag,480,2024-09-12,GB")

    def test_a_weight_of_nothing(self) -> None:
        assert "cannot weigh nothing" in self.problem(
            "L-2024-0041,wheat,0,bag,480,2024-09-12,GB"
        )

    def test_a_way_of_putting_seed_up_that_is_not_one(self) -> None:
        detail = self.problem("L-2024-0041,wheat,24000,barrels,480,2024-09-12,GB")

        assert "not a way of putting seed up" in detail
        assert "bag" in detail

    def test_a_container_count_that_is_not_a_count(self) -> None:
        assert "whole number" in self.problem(
            "L-2024-0041,wheat,24000,bag,about 480,2024-09-12,GB"
        )

    def test_a_date_written_the_way_the_paperwork_writes_it(self) -> None:
        assert "not a date" in self.problem("L-2024-0041,wheat,24000,bag,480,12/09/2024,GB")

    def test_an_origin_written_out_in_full(self) -> None:
        assert "two letter country" in self.problem(
            "L-2024-0041,wheat,24000,bag,480,2024-09-12,United Kingdom"
        )

    def test_the_problem_quotes_what_was_typed(self) -> None:
        problem = parse(
            a_file("L-2024-0041,wheat,24000,bag,480,12/09/2024,GB"), MERCHANT
        ).problems[0]

        assert problem.value == "12/09/2024"
        assert "12/09/2024" in str(problem)

    def test_a_row_that_is_wrong_in_two_ways_reports_the_first(self) -> None:
        # One reason per row. A merchant fixing a spreadsheet works down the
        # list, and three lines about one row reads as three problems.
        read = parse(a_file("L-nonsense,quinoa,24000,bag,480,2024-09-12,GB"), MERCHANT)

        assert len(read.problems) == 1
