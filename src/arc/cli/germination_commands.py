"""Recording a germination test from the bench.

The trays are typed in as they were counted, one option per tray, in the five
categories in the order they appear on the worksheet. That looks fussy next to
a single germination percentage, and it is the point: the station records what
was counted and works the percentage out, rather than recording somebody's
arithmetic.
"""

from __future__ import annotations

from datetime import datetime

import click

from arc.cli.context import Context
from arc.cli.station import open_station
from arc.germination.dormancy import assess, check_treatment, treatments_for
from arc.germination.model import GerminationTest, Replicate, Treatment, check_test
from arc.germination.outcome import decide
from arc.germination.tolerance import check_range
from arc.species import register

__all__ = ["germination"]


def _replicate(raw: str) -> Replicate:
    """Reads one tray, written normal,abnormal,hard,fresh,dead."""
    parts = raw.split(",")
    if len(parts) != 5:
        raise click.BadParameter(
            f"{raw!r} is not a tray, write it as normal,abnormal,hard,fresh,dead"
        )
    try:
        counts = [int(part.strip()) for part in parts]
    except ValueError as error:
        raise click.BadParameter(f"{raw!r} has something in it that is not a count") from error

    return Replicate(
        normal=counts[0],
        abnormal=counts[1],
        hard=counts[2],
        fresh=counts[3],
        dead=counts[4],
    )


@click.group()
def germination() -> None:
    """Germination tests: four hundred seeds, counted."""


@germination.command("record")
@click.argument("reference")
@click.option(
    "--tray",
    "trays",
    multiple=True,
    required=True,
    help="One per tray, as normal,abnormal,hard,fresh,dead.",
)
@click.option("--seeds", type=int, default=100, show_default=True, help="Seeds per tray.")
@click.option("--set-down", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.option("--final-count", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.option("--analyst", required=True)
@click.option("--retest", is_flag=True, help="This is the repeat of an earlier test.")
@click.option(
    "--treatment",
    type=click.Choice([treatment.value for treatment in Treatment]),
    default=Treatment.NONE.value,
    show_default=True,
    help="What was done to the sample to get it out of dormancy.",
)
@click.pass_obj
def record(
    context: Context,
    reference: str,
    trays: tuple[str, ...],
    seeds: int,
    set_down: datetime,
    final_count: datetime,
    analyst: str,
    retest: bool,
    treatment: str,
) -> None:
    """Record one germination test and say what it comes to."""
    station = open_station(context.database)
    lot = station.lots.require(reference)

    test = GerminationTest(
        lot_reference=reference,
        species_name=lot.species_name,
        replicates=tuple(_replicate(raw) for raw in trays),
        seeds_per_replicate=seeds,
        set_down_on=set_down.date(),
        final_count_on=final_count.date(),
        analyst=analyst,
        is_retest=retest,
        treatment=Treatment(treatment),
    )

    species = register.require(lot.species_name)
    broken = check_test(test) + check_treatment(test, species)
    if broken:
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2)

    station.germination.record(test)

    spread = check_range(test.mean_normal, test.replicate_range)
    dormancy = assess(test)
    context.say(f"recorded against {reference}")
    click.echo(f"germination {test.mean_normal} percent")
    click.echo(spread.explain())

    if dormancy.hard_seed_is_reportable:
        click.echo(f"hard seed {dormancy.hard_percent} percent")
    if dormancy.is_dormant:
        click.echo(dormancy.explain())

    if spread.must_be_repeated:
        click.echo("the test has to be set down again", err=True)
        raise SystemExit(2)


@germination.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """Every germination test on a lot, and what the station will report."""
    station = open_station(context.database)
    station.lots.require(reference)
    tests = station.germination.for_lot(reference)

    if not tests:
        click.echo("nothing set down yet")
        return

    for index, test in enumerate(tests, start=1):
        marker = " (repeat)" if test.is_retest else ""
        click.echo(
            f"{index}. set down {test.set_down_on}, " f"counted {test.final_count_on}{marker}"
        )
        click.echo(
            "   trays "
            + "  ".join(str(tray.normal) for tray in test.replicates)
            + f"   mean {test.mean_normal}   spread {test.replicate_range}"
        )
        if test.treatment.was_applied:
            click.echo(f"   after {test.treatment.value}")

    outcome = decide(tests[0], tests[1] if len(tests) > 1 else None)
    click.echo(f"verdict: {outcome.verdict.value}")
    click.echo(f"  {outcome.reason}")
    if outcome.reported_percent is not None:
        click.echo(f"  reporting {outcome.reported_percent} percent")


@germination.command("treatments")
@click.argument("species_name")
def treatments(species_name: str) -> None:
    """Which treatments the handbook allows for a species."""
    species = register.require(species_name)

    click.echo(f"{species.botanical_name} ({species.common_name})")
    for treatment in treatments_for(species):
        click.echo(f"  {treatment.value}")
