"""Looking a species up from the terminal."""

from __future__ import annotations

import pytest

from arc.errors import NotFound


class TestListing:
    def test_it_lists_every_species_the_station_takes(self, run) -> None:
        result = run("species", "list")

        assert result.exit_code == 0
        assert "Triticum aestivum" in result.output
        assert "Lolium perenne" in result.output
        assert result.output.count("\n") == 26

    def test_it_puts_the_common_name_next_to_the_botanical_one(self, run) -> None:
        result = run("species", "list")

        # The column is padded to the longest botanical name in the list.
        assert "Triticum aestivum     wheat" in result.output

    def test_it_lists_in_botanical_order(self, run) -> None:
        lines = run("species", "list").output.strip().splitlines()
        names = [line.split("  ")[0] for line in lines]

        assert names == sorted(names)

    def test_a_class_can_be_asked_for_on_its_own(self, run) -> None:
        result = run("species", "list", "--seed-class", "grass")

        assert "Lolium perenne" in result.output
        assert "Triticum aestivum" not in result.output

    def test_the_class_is_not_case_sensitive(self, run) -> None:
        assert run("species", "list", "--seed-class", "GRASS").exit_code == 0

    def test_a_class_nobody_has_is_refused_with_the_list(self, run) -> None:
        result = run("species", "list", "--seed-class", "fungus")

        assert result.exit_code != 0
        assert "cereal" in result.output

    def test_the_chaffy_ones_can_be_pulled_out(self, run) -> None:
        result = run("species", "list", "--chaffy")

        assert "Lolium perenne" in result.output
        assert "Triticum aestivum" not in result.output

    def test_the_filters_stack(self, run) -> None:
        both = run("species", "list", "--seed-class", "cereal", "--chaffy").output

        assert "Avena sativa" in both
        assert "Triticum aestivum" not in both


class TestShowing:
    def test_it_prints_the_numbers_the_analyst_came_for(self, run) -> None:
        output = run("species", "show", "wheat").output

        assert "Triticum aestivum (wheat)" in output
        assert "30000 kg" in output
        assert "1000 g" in output
        assert "120 g" in output

    def test_it_prints_the_germination_method(self, run) -> None:
        output = run("species", "show", "wheat").output

        assert "BP at 20" in output
        assert "count day 4 to 8" in output

    def test_a_prechill_is_only_mentioned_when_there_is_one(self, run) -> None:
        assert "prechill" not in run("species", "show", "wheat").output
        assert "prechill" in run("species", "show", "perennial ryegrass").output

    def test_the_aliases_are_listed_when_there_are_any(self, run) -> None:
        assert "also called" in run("species", "show", "wheat").output
        assert "also called" not in run("species", "show", "barley").output

    def test_a_common_name_or_an_alias_finds_it_too(self, run) -> None:
        by_alias = run("species", "show", "canola").output

        assert "Brassica napus" in by_alias

    def test_a_species_the_station_cannot_test_is_refused(self, run) -> None:
        with pytest.raises(NotFound):
            run("species", "show", "Triticum durum")

    def test_a_near_miss_gets_suggestions(self, run) -> None:
        try:
            run("species", "show", "Triticum")
        except NotFound:
            pass
        else:  # pragma: no cover - the command is expected to refuse
            raise AssertionError("expected a refusal")


class TestTheTopLevel:
    def test_it_says_who_the_station_is(self, run) -> None:
        result = run("station")

        assert "Ravenscar Seed Testing Station" in result.output
        assert "GB-0214" in result.output

    def test_quiet_leaves_out_everything_but_the_answer(self, run) -> None:
        loud = run("station").output
        quiet = run("--quiet", "station").output

        assert "database" in loud
        assert "database" not in quiet
        assert "Ravenscar" in quiet

    def test_the_version_is_the_package_version(self, run) -> None:
        from arc import __version__

        result = run("--version")

        assert __version__ in result.output

    def test_help_lists_the_groups(self, run) -> None:
        output = run("--help").output

        assert "species" in output
        assert "station" in output
