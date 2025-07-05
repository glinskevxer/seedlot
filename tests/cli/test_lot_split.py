"""Splitting a consignment, from the console.

Forty tonnes of wheat against a thirty tonne maximum is two lots. The
arithmetic that matters is that the sublots add back up to what arrived: a
consignment divided three ways cannot be three equal parts, and a station whose
paperwork loses a kilogram somewhere has paperwork nobody can reconcile.
"""

from __future__ import annotations

import re
from decimal import Decimal


def listed_weights(run) -> list[Decimal]:
    """The weights on the open lots, read off the list the way a person does."""
    return [
        Decimal(found.group(1))
        for line in run("lot", "list").output.splitlines()
        if (found := re.search(r"([0-9.]+) kg", line))
    ]


def split(run, *, weight: str = "40000", reference: str = "L-2024-0050", start: str = "51"):
    return run(
        "lot",
        "split",
        reference,
        "--species",
        "wheat",
        "--weight",
        weight,
        "--containers",
        "bag",
        "--container-count",
        "800",
        "--merchant",
        "Ravenscar Grain",
        "--sealed-on",
        "2024-09-12",
        "--origin",
        "GB",
        "--sublots-from",
        start,
    )


class TestSplittingAConsignment:
    def test_forty_tonnes_of_wheat_becomes_two_lots(self, run) -> None:
        result = split(run)

        assert result.exit_code == 0
        assert "L-2024-0051" in result.output
        assert "L-2024-0052" in result.output

    def test_the_sublots_add_back_up_to_what_arrived(self, run) -> None:
        split(run)

        assert sum(listed_weights(run)) == Decimal("40000")

    def test_each_sublot_is_inside_the_maximum(self, run) -> None:
        split(run)

        assert all(weight <= Decimal("30000") for weight in listed_weights(run))

    def test_the_containers_are_shared_out_too(self, run) -> None:
        split(run)

        first = run("lot", "show", "L-2024-0051").output
        second = run("lot", "show", "L-2024-0052").output

        assert "containers  400" in first
        assert "containers  400" in second

    def test_three_ways_still_adds_up(self, run) -> None:
        # Seventy tonnes over a thirty tonne maximum is three, and seventy
        # does not divide by three, so one of them carries the remainder.
        split(run, weight="70000")

        weights = listed_weights(run)

        assert len(weights) == 3
        assert sum(weights) == Decimal("70000")
        assert len(set(weights)) == 2


class TestTheConsignmentItself:
    def test_it_is_recorded(self, run) -> None:
        split(run)

        assert run("lot", "show", "L-2024-0050").exit_code == 0

    def test_and_it_is_closed_because_nobody_can_test_it(self, run) -> None:
        split(run)

        assert "closed" in run("lot", "show", "L-2024-0050").output

    def test_the_sublots_point_at_it(self, run) -> None:
        split(run)

        shown = run("lot", "show", "L-2024-0051").output

        assert "sublot of   L-2024-0050" in shown

    def test_and_it_lists_them(self, run) -> None:
        split(run)

        shown = run("lot", "show", "L-2024-0050").output

        assert "L-2024-0051" in shown
        assert "L-2024-0052" in shown

    def test_the_split_goes_in_the_day_book(self, run) -> None:
        split(run)

        assert "split L-2024-0050: into 2 sublots" in run("journal").output


class TestWhatIsRefused:
    def test_a_consignment_that_did_not_need_splitting(self, run) -> None:
        result = split(run, weight="24000")

        assert result.exit_code == 2
        assert "inside the 30000 kg maximum" in result.output

    def test_a_consignment_already_booked_in(self, run) -> None:
        split(run)

        result = split(run)

        assert result.exit_code == 2
        assert "booked in already" in result.output

    def test_sublot_serials_that_are_already_in_use(self, run) -> None:
        split(run)

        result = split(run, reference="L-2024-0060", start="51")

        assert result.exit_code == 2
        assert "already in use" in result.output

    def test_nothing_is_written_when_it_is_refused(self, run) -> None:
        split(run, weight="24000")

        assert "nothing booked in" in run("lot", "list").output.lower() or (
            "L-2024-0050" not in run("lot", "list").output
        )


class TestTheSublotsAreRealLots:
    def test_one_can_be_tested_and_certified(self, run) -> None:
        split(run)
        run(
            "purity",
            "record",
            "L-2024-0051",
            "--working",
            "120.0",
            "--pure",
            "118.2",
            "--other",
            "0.9",
            "--inert",
            "0.9",
            "--analyst",
            "J. Whitfield",
        )
        run(
            "germination",
            "record",
            "L-2024-0051",
            "--tray",
            "96,4,0,0,0",
            "--tray",
            "95,5,0,0,0",
            "--tray",
            "97,3,0,0,0",
            "--tray",
            "96,4,0,0,0",
            "--set-down",
            "2024-09-20",
            "--final-count",
            "2024-09-28",
            "--analyst",
            "J. Whitfield",
        )

        result = run("certificate", "issue", "L-2024-0051", "--signed-by", "A. Pearce")

        assert result.exit_code == 0

    def test_and_its_certificate_carries_its_own_weight(self, run) -> None:
        split(run)
        run(
            "purity",
            "record",
            "L-2024-0051",
            "--working",
            "120.0",
            "--pure",
            "118.2",
            "--other",
            "0.9",
            "--inert",
            "0.9",
            "--analyst",
            "J. Whitfield",
        )
        run(
            "germination",
            "record",
            "L-2024-0051",
            "--tray",
            "96,4,0,0,0",
            "--tray",
            "95,5,0,0,0",
            "--tray",
            "97,3,0,0,0",
            "--tray",
            "96,4,0,0,0",
            "--set-down",
            "2024-09-20",
            "--final-count",
            "2024-09-28",
            "--analyst",
            "J. Whitfield",
        )
        run("certificate", "issue", "L-2024-0051", "--signed-by", "A. Pearce")

        printed = run("certificate", "print", "GB-0214/2024/00001").output

        assert "20000 kg" in printed
        assert "40000" not in printed
