"""The refusal shapes, before anything is built on top of them."""

from __future__ import annotations

import pytest

from arc.errors import ConfigurationError, NotFound, OutOfOrder, Rule, RuleBroken


def test_a_rule_reads_as_a_sentence_with_its_code_in_front() -> None:
    rule = Rule("LOT_TOO_HEAVY", "the lot is over the maximum for wheat")

    assert str(rule) == "LOT_TOO_HEAVY: the lot is over the maximum for wheat"


def test_a_rule_names_its_subject_when_it_has_one() -> None:
    rule = Rule("LOT_TOO_HEAVY", "over the maximum", subject="L-2024-0041")

    assert str(rule) == "LOT_TOO_HEAVY (L-2024-0041): over the maximum"


def test_a_rule_without_a_code_or_a_detail_is_a_programming_mistake() -> None:
    with pytest.raises(ValueError, match="needs a code"):
        Rule("", "something")

    with pytest.raises(ValueError, match="needs a detail"):
        Rule("SOMETHING", "")


def test_one_broken_rule_reads_as_that_rule() -> None:
    refusal = RuleBroken.one("REPLICATE_RANGE", "the four replicates are too far apart")

    assert str(refusal) == "the four replicates are too far apart"
    assert refusal.codes == ["REPLICATE_RANGE"]


def test_several_broken_rules_are_counted_rather_than_run_together() -> None:
    refusal = RuleBroken(
        [
            Rule("REPLICATE_RANGE", "the four replicates are too far apart"),
            Rule("SAMPLE_TOO_SMALL", "the working sample was under weight"),
        ]
    )

    assert str(refusal) == "2 rules were not satisfied"
    assert refusal.codes == ["REPLICATE_RANGE", "SAMPLE_TOO_SMALL"]


def test_a_refusal_with_nothing_in_it_is_a_programming_mistake() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        RuleBroken([])


def test_a_refusal_is_still_an_exception_that_can_be_caught_broadly() -> None:
    with pytest.raises(RuleBroken) as caught:
        raise RuleBroken.one("ANY", "anything")

    assert caught.value.rules[0].code == "ANY"


def test_a_missing_thing_says_what_was_looked_for_and_what_by() -> None:
    error = NotFound("species", "Triticum aestivum")

    assert "species" in str(error)
    assert "Triticum aestivum" in str(error)
    assert error.what == "species"
    assert error.identifier == "Triticum aestivum"


def test_the_other_two_shapes_carry_their_message_through() -> None:
    assert "germination" in str(OutOfOrder("germination before purity"))
    assert "no station code" in str(ConfigurationError("no station code is set"))
