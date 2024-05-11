"""Writing a sheet somebody will open in a spreadsheet."""

from __future__ import annotations

from arc.reporting.csv_writer import CsvWriter, quote


class TestQuoting:
    def test_every_value_is_quoted_whether_it_needs_it_or_not(self) -> None:
        assert quote("wheat") == '"wheat"'
        assert quote(96) == '"96"'

    def test_a_comma_inside_a_value_does_not_become_a_new_column(self) -> None:
        assert quote("Ravenscar Grain, Whitby") == '"Ravenscar Grain, Whitby"'

    def test_a_quote_inside_a_value_is_doubled(self) -> None:
        assert quote('the "pure" fraction') == '"the ""pure"" fraction"'

    def test_a_newline_stays_inside_the_quotes(self) -> None:
        assert quote("one\ntwo") == '"one\ntwo"'

    def test_nothing_is_written_as_empty_rather_than_the_word_none(self) -> None:
        assert quote(None) == '""'

    def test_a_value_a_spreadsheet_would_run_is_defused(self) -> None:
        assert quote("=SUM(A1:A9)") == "\"'=SUM(A1:A9)\""
        assert quote("+441947") == "\"'+441947\""
        assert quote("-12") == "\"'-12\""
        assert quote("@ravenscar") == "\"'@ravenscar\""

    def test_an_ordinary_value_is_left_exactly_as_it_was(self) -> None:
        assert quote("Triticum aestivum") == '"Triticum aestivum"'


class TestBuildingASheet:
    def test_an_empty_sheet_is_empty_rather_than_a_blank_line(self) -> None:
        assert CsvWriter().to_csv() == ""

    def test_a_header_is_the_first_row(self) -> None:
        sheet = CsvWriter(["lot", "species"])

        assert sheet.to_csv() == '"lot","species"\r\n'

    def test_rows_come_out_in_the_order_they_went_in(self) -> None:
        sheet = CsvWriter(["lot", "germination"])
        sheet.row("L-2024-0041", 96)
        sheet.row("L-2024-0042", 92)

        assert sheet.to_csv().splitlines() == [
            '"lot","germination"',
            '"L-2024-0041","96"',
            '"L-2024-0042","92"',
        ]

    def test_rows_can_be_added_in_one_go(self) -> None:
        sheet = CsvWriter(["lot"]).rows([["L-2024-0041"], ["L-2024-0042"]])

        assert len(sheet) == 3

    def test_the_line_ending_is_the_one_the_format_asks_for(self) -> None:
        assert CsvWriter(["lot"]).to_csv().endswith("\r\n")

    def test_building_a_sheet_reads_as_a_chain(self) -> None:
        sheet = CsvWriter(["lot"]).row("L-2024-0041").row("L-2024-0042")

        assert len(sheet) == 3
