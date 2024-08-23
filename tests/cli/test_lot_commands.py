"""Booking lots in from the terminal."""

from __future__ import annotations

import pytest


def book(
    run,
    *,
    reference="L-2024-0041",
    species="wheat",
    weight="24000",
    containers="bag",
    count="480",
    merchant="Ravenscar Grain",
    sealed="2024-09-12",
    origin="GB",
):
    return run(
        "lot",
        "book-in",
        reference,
        "--species",
        species,
        "--weight",
        weight,
        "--containers",
        containers,
        "--container-count",
        count,
        "--merchant",
        merchant,
        "--sealed-on",
        sealed,
        "--origin",
        origin,
    )


class TestBookingIn:
    def test_a_good_lot_is_accepted_and_gets_its_docket(self, run) -> None:
        result = book(run)

        assert result.exit_code == 0
        assert "booked in L-2024-0041" in result.output
        assert "Take 30 primary samples" in result.output
        assert "Submit at least 1000 g" in result.output

    def test_the_docket_names_the_species_botanically(self, run) -> None:
        assert "Species Triticum aestivum" in book(run).output

    def test_a_common_name_is_enough_to_book_with(self, run) -> None:
        assert book(run, species="wheat").exit_code == 0

    def test_the_lot_is_there_afterwards(self, run) -> None:
        book(run)

        shown = run("lot", "show", "L-2024-0041")

        assert "Triticum aestivum" in shown.output
        assert "24000 kg" in shown.output
        assert "booked in" in shown.output

    def test_bulk_gets_a_stream_docket_and_no_container_line(self, run) -> None:
        result = book(run, containers="bulk", count="0")

        assert "Sample in stream" in result.output
        assert "Open at least" not in result.output

    def test_a_species_the_station_cannot_test_is_refused(self, run) -> None:
        from arc.errors import NotFound

        with pytest.raises(NotFound):
            book(run, species="Triticum durum")

    def test_a_lot_over_the_maximum_is_refused_with_advice(self, run) -> None:
        result = book(run, weight="90000")

        assert result.exit_code == 2
        assert "refused" in result.output
        assert "split it into 3 sublots" in result.output

    def test_a_refused_lot_is_not_written_to_the_database(self, run) -> None:
        book(run, weight="90000")

        assert "nothing open" in run("lot", "list").output

    def test_a_weight_that_is_not_a_number_is_refused_before_anything_else(self, run) -> None:
        result = book(run, weight="lots")

        assert result.exit_code != 0
        assert "not a weight" in result.output

    def test_a_reference_in_the_wrong_shape_is_refused(self, run) -> None:
        with pytest.raises(ValueError, match="not a lot reference"):
            book(run, reference="2024-41")


class TestLookingAtLots:
    def test_an_empty_station_says_so(self, run) -> None:
        assert "nothing open" in run("lot", "list").output

    def test_lots_are_listed_oldest_first(self, run) -> None:
        book(run, reference="L-2024-0041")
        book(run, reference="L-2024-0042", weight="12000", count="240")

        lines = run("lot", "list").output.strip().splitlines()

        assert "L-2024-0041" in lines[0]
        assert "L-2024-0042" in lines[1]

    def test_the_listing_carries_the_weight_and_the_status(self, run) -> None:
        book(run)

        line = run("lot", "list").output.strip()

        assert "24000 kg" in line
        assert "booked in" in line

    def test_one_species_can_be_pulled_out(self, run) -> None:
        book(run, reference="L-2024-0041", species="wheat")
        book(
            run,
            reference="L-2024-0077",
            species="perennial ryegrass",
            weight="8000",
            count="320",
        )

        only_grass = run("lot", "list", "--species", "Lolium perenne").output

        assert "L-2024-0077" in only_grass
        assert "L-2024-0041" not in only_grass

    def test_a_lot_nobody_booked_in_is_not_found(self, run) -> None:
        from arc.errors import NotFound

        with pytest.raises(NotFound):
            run("lot", "show", "L-2024-9999")

    def test_a_bulk_lot_does_not_print_a_container_count(self, run) -> None:
        book(run, containers="bulk", count="0")

        assert "containers" not in run("lot", "show", "L-2024-0041").output
