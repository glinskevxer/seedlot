"""A consignment through the station from the lorry to the shelf.

One test that runs the whole thing in order, because every other test in this
suite checks one step and none of them would notice if two steps stopped
fitting together. It is deliberately written as one long walk rather than split
into pieces: the order is the point, and a fixture that set up step four would
be a fixture that hid whether step three produced it.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def console(run):
    return run


def test_a_consignment_from_the_lorry_to_the_shelf(console) -> None:
    # Forty tonnes of wheat arrives, which is over the thirty tonne maximum,
    # so it becomes two lots before anything is tested.
    split = console(
        "lot",
        "split",
        "L-2024-0050",
        "--species",
        "wheat",
        "--weight",
        "40000",
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
        "51",
    )
    assert split.exit_code == 0
    assert "L-2024-0051" in split.output
    assert "L-2024-0052" in split.output

    # Both sublots are on the Monday list with a date against them.
    monday = console("report", "work")
    assert "L-2024-0051" in monday.output
    assert "due 2024-10-13" in monday.output

    # The purity analysis. The station is given the weighings and works the
    # percentages out itself.
    purity = console(
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
    assert purity.exit_code == 0
    assert "98.4" in purity.output

    # The lot is on the bench now, which nothing had to be told.
    assert "in test" in console("lot", "show", "L-2024-0051").output

    # The first germination comes back dormant, so it cannot be reported.
    dormant = console(
        "germination",
        "record",
        "L-2024-0051",
        "--tray",
        "80,4,0,16,0",
        "--tray",
        "80,4,0,16,0",
        "--tray",
        "80,4,0,16,0",
        "--tray",
        "80,4,0,16,0",
        "--set-down",
        "2024-09-20",
        "--final-count",
        "2024-09-28",
        "--analyst",
        "J. Whitfield",
    )
    assert dormant.exit_code == 2
    assert "test it again" in dormant.output

    # Prechilled and repeated, it settles.
    repeated = console(
        "germination",
        "record",
        "L-2024-0051",
        "--tray",
        "94,4,0,2,0",
        "--tray",
        "93,5,0,2,0",
        "--tray",
        "95,3,0,2,0",
        "--tray",
        "94,4,0,2,0",
        "--set-down",
        "2024-09-20",
        "--final-count",
        "2024-09-28",
        "--analyst",
        "J. Whitfield",
        "--treatment",
        "prechill",
        "--retest",
    )
    assert repeated.exit_code == 0
    assert "germination 94 percent" in repeated.output

    # A search for other species, through ten times the purity sample.
    search = console(
        "otherseed",
        "record",
        "L-2024-0051",
        "--weight",
        "1200.0",
        "--found",
        "Avena fatua=4",
        "--analyst",
        "J. Whitfield",
    )
    assert search.exit_code == 0
    assert "3.3 per kg" in search.output

    # The certificate. It carries the treatment, because a germination after a
    # prechill is a different claim from one without.
    issued = console("certificate", "issue", "L-2024-0051", "--signed-by", "A. Pearce")
    assert issued.exit_code == 0
    assert "GB-2024" in issued.output or "GB-0214/2024/00001" in issued.output

    printed = console("certificate", "print", "GB-0214/2024/00001")
    assert "after prechill" in printed.output
    assert "Avena fatua 4 in 1200.0 g" in printed.output
    assert "20000 kg" in printed.output

    # The lot comes off the Monday list and the other sublot does not.
    monday = console("report", "work")
    assert "L-2024-0051" not in monday.output
    assert "L-2024-0052" in monday.output

    # What is left of the sample goes on the shelf, held for a year.
    jar = console("store", "show", "L-2024-0051")
    assert "hold until  2025-10-02" in jar.output
    assert "860.0 g" in jar.output

    # The merchant disputes the germination. Another laboratory gets 91, which
    # is inside the allowance between laboratories, so the result stands.
    dispute = console(
        "referee",
        "compare",
        "L-2024-0051",
        "--certificate",
        "GB-0214/2024/00001",
        "--for",
        "germination",
        "--theirs",
        "91",
        "--laboratory",
        "NL-0510 Wageningen",
        "--raised-by",
        "Ravenscar Grain",
    )
    assert dispute.exit_code == 0
    assert "the first result stands" in dispute.output

    # A repeat purity is drawn from the jar to settle it.
    drawn = console(
        "store",
        "draw",
        "L-2024-0051",
        "--for",
        "purity",
        "--analyst",
        "R. Naylor",
    )
    assert drawn.exit_code == 0
    assert "740.0 g left" in drawn.output

    # A search cannot be repeated from what is left, and the refusal says so
    # rather than silently doing a smaller one.
    refused = console(
        "store",
        "draw",
        "L-2024-0051",
        "--for",
        "other seed by number",
        "--analyst",
        "R. Naylor",
    )
    assert refused.exit_code == 2
    assert "460.0 g short" in refused.output

    # A year later the jar comes off the shelf.
    assert "nothing is due" in console("store", "due").output
    due = console("--today", "2025-10-03", "store", "due")
    assert "L-2024-0051" in due.output
    assert console("--today", "2025-10-03", "store", "dispose", "L-2024-0051").exit_code == 0

    # And the day book has the whole thing in it, in order.
    book = console("journal", "--subject", "L-2024-0051").output.splitlines()
    assert len(book) >= 6
    assert any("recorded a purity" in line for line in book)
    assert any("recorded a germination" in line for line in book)
    assert any("searched for other seed" in line for line in book)
    assert any("drew from the store" in line for line in book)
    assert any("disposed of the sample" in line for line in book)

    # The doctor is happy about all of it except the certificate whose sample
    # has now gone, which is exactly the thing it is there to notice.
    doctor = console("--today", "2025-10-04", "doctor")
    assert doctor.exit_code == 1
    assert "CERTIFICATE_WITHOUT_A_SAMPLE" in doctor.output
