"""The sample store, driven from the console.

A jar only appears once a certificate has been issued, so every test here books
a lot in, tests it and certifies it first. The fixture does that in four
commands, which is what it takes on a real morning too.
"""

from __future__ import annotations

import pytest

from arc.errors import NotFound


@pytest.fixture
def certified(run):
    run(
        "lot",
        "book-in",
        "L-2024-0041",
        "--species",
        "wheat",
        "--weight",
        "24000",
        "--containers",
        "bag",
        "--container-count",
        "480",
        "--merchant",
        "Ravenscar Grain",
        "--sealed-on",
        "2024-09-12",
        "--origin",
        "GB",
    )
    run(
        "purity",
        "record",
        "L-2024-0041",
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
        "L-2024-0041",
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
    run("certificate", "issue", "L-2024-0041", "--signed-by", "A. Pearce")
    return run


class TestLookingAtAJar:
    def test_a_certified_lot_has_one(self, certified) -> None:
        result = certified("store", "show", "L-2024-0041")

        assert result.exit_code == 0
        assert "860.0 g" in result.output

    def test_it_says_how_long_it_is_held(self, certified) -> None:
        result = certified("store", "show", "L-2024-0041")

        assert "hold until  2025-10-02" in result.output

    def test_it_lists_what_could_still_be_done(self, certified) -> None:
        result = certified("store", "show", "L-2024-0041")

        assert "purity" in result.output
        assert "germination" in result.output

    def test_and_leaves_out_what_could_not(self, certified) -> None:
        result = certified("store", "show", "L-2024-0041")

        assert "other seed by number" not in result.output

    def test_a_lot_with_no_jar_refuses(self, run) -> None:
        with pytest.raises(NotFound, match="retained sample"):
            run("store", "show", "L-2024-0041")


class TestTheStoreList:
    def test_an_empty_store_says_so(self, run) -> None:
        assert "the store is empty" in run("store", "list").output

    def test_a_held_jar_is_listed(self, certified) -> None:
        result = certified("store", "list")

        assert "L-2024-0041" in result.output
        assert "days left" in result.output

    def test_nothing_is_due_yet(self, certified) -> None:
        assert "nothing is due" in certified("store", "due").output


class TestDrawingFromAJar:
    def test_a_purity_repeat_comes_off_the_weight(self, certified) -> None:
        result = certified(
            "store", "draw", "L-2024-0041", "--for", "purity", "--analyst", "R. Naylor"
        )

        assert result.exit_code == 0
        assert "740.0 g left" in result.output

    def test_the_default_weight_is_the_working_sample(self, certified) -> None:
        result = certified(
            "store", "draw", "L-2024-0041", "--for", "purity", "--analyst", "R. Naylor"
        )

        assert "drew 120 g" in result.output

    def test_a_weight_can_be_given_instead(self, certified) -> None:
        result = certified(
            "store",
            "draw",
            "L-2024-0041",
            "--for",
            "purity",
            "--analyst",
            "R. Naylor",
            "--weight",
            "130.0",
        )

        assert "730.0 g left" in result.output

    def test_a_search_is_refused_because_the_jar_is_too_small(self, certified) -> None:
        result = certified(
            "store",
            "draw",
            "L-2024-0041",
            "--for",
            "other seed by number",
            "--analyst",
            "R. Naylor",
        )

        assert result.exit_code == 2
        assert "340.0 g short" in result.output

    def test_and_the_jar_is_untouched_after_a_refusal(self, certified) -> None:
        certified(
            "store",
            "draw",
            "L-2024-0041",
            "--for",
            "other seed by number",
            "--analyst",
            "R. Naylor",
        )

        assert "860.0 g" in certified("store", "show", "L-2024-0041").output

    def test_draws_stack_up(self, certified) -> None:
        certified("store", "draw", "L-2024-0041", "--for", "purity", "--analyst", "R. Naylor")
        result = certified(
            "store",
            "draw",
            "L-2024-0041",
            "--for",
            "germination",
            "--analyst",
            "R. Naylor",
        )

        assert "720.0 g left" in result.output


class TestThrowingAJarOut:
    def test_a_jar_inside_its_period_is_refused(self, certified) -> None:
        result = certified("store", "dispose", "L-2024-0041")

        assert result.exit_code == 2
        assert "days away" in result.output
        assert "use --force" in result.output

    def test_forcing_it_needs_a_reason_that_is_not_the_calendar(self, certified) -> None:
        result = certified("store", "dispose", "L-2024-0041", "--force")

        assert result.exit_code != 0
        assert "say why it is going" in result.output

    def test_forcing_it_with_a_real_reason_works(self, certified) -> None:
        result = certified(
            "store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store"
        )

        assert result.exit_code == 0

    def test_and_the_jar_then_reads_as_gone(self, certified) -> None:
        certified("store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store")

        shown = certified("store", "show", "L-2024-0041")

        assert "disposed" in shown.output
        assert "spoiled in store" in shown.output

    def test_nothing_can_be_drawn_from_it_afterwards(self, certified) -> None:
        certified("store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store")

        result = certified(
            "store", "draw", "L-2024-0041", "--for", "purity", "--analyst", "R. Naylor"
        )

        assert result.exit_code == 2
        assert "nothing to repeat the test on" in result.output

    def test_and_it_drops_off_the_store_list(self, certified) -> None:
        certified("store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store")

        assert "the store is empty" in certified("store", "list").output

    def test_disposing_of_it_twice_is_refused(self, certified) -> None:
        certified("store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store")
        result = certified(
            "store", "dispose", "L-2024-0041", "--force", "--reason", "spoiled in store"
        )

        assert result.exit_code == 2
        assert "went on" in result.output


class TestOnceThePeriodHasRun:
    def test_the_jar_shows_as_due(self, certified) -> None:
        result = certified("--today", "2025-10-03", "store", "due")

        assert "L-2024-0041" in result.output
        assert "overdue" in result.output

    def test_and_can_be_thrown_out_without_forcing(self, certified) -> None:
        result = certified("--today", "2025-10-03", "store", "dispose", "L-2024-0041")

        assert result.exit_code == 0

    def test_a_repeat_is_flagged_as_no_longer_backing_the_certificate(self, certified) -> None:
        result = certified(
            "--today",
            "2025-10-03",
            "store",
            "draw",
            "L-2024-0041",
            "--for",
            "purity",
            "--analyst",
            "R. Naylor",
        )

        assert result.exit_code == 2
        assert "no longer the one the certificate is backed by" in result.output
