"""Recording a purity analysis from the bench."""

from __future__ import annotations

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.purity.analysis import analyse, check_analysis
from arc.purity.tolerance import compare
from arc.species import register
from arc.workflow.progress import begin_testing

__all__ = ["purity"]


@click.group()
def purity() -> None:
    """Purity analyses: what the sample is made of."""


@purity.command("record")
@click.argument("reference")
@click.option("--working", required=True, help="What went on the board, in grams.")
@click.option("--pure", required=True, help="Pure seed, in grams.")
@click.option("--other", required=True, help="Other seed, in grams.")
@click.option("--inert", required=True, help="Inert matter, in grams.")
@click.option("--analyst", required=True)
@click.option("--duplicate", is_flag=True, help="This is the second analysis.")
@click.pass_obj
def record(
    context: Context,
    reference: str,
    working: str,
    pure: str,
    other: str,
    inert: str,
    analyst: str,
    duplicate: bool,
) -> None:
    """Record one analysis and print what it comes to."""
    from arc.purity.analysis import PurityAnalysis

    station = context.station()
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)

    analysis = PurityAnalysis(
        working_sample_g=weight_option(working),
        pure_seed_g=weight_option(pure),
        other_seed_g=weight_option(other),
        inert_matter_g=weight_option(inert),
        analyst=analyst,
    )

    broken = check_analysis(analysis, species)
    if broken:
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        # It is still recorded. An analysis that was void is part of what
        # happened to the sample and the next one has to be comparable to it.
        station.purity.record(
            reference, analysis, None, analysed_on=context.today, is_duplicate=duplicate
        )
        raise SystemExit(2)

    result = analyse(analysis, species)
    station.purity.record(
        reference, analysis, result, analysed_on=context.today, is_duplicate=duplicate
    )

    begin_testing(lot, station.lots, on=context.today)
    context.record(station, "recorded a purity for", reference, f"by {analyst}")
    context.say(f"recorded against {reference}")
    click.echo(f"pure seed    {result.pure_seed}")
    click.echo(f"other seed   {result.other_seed}")
    click.echo(f"inert matter {result.inert_matter}")
    if result.loss_fraction:
        lost = (result.loss_fraction * 100).quantize(analysis.working_sample_g)
        context.say(f"lost {lost} percent on the board")


@purity.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """Every analysis of one lot, and whether the duplicates agree."""
    station = context.station()
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)
    analyses = station.purity.for_lot(reference)

    if not analyses:
        click.echo("nothing analysed yet")
        return

    for index, stored in enumerate(analyses, start=1):
        marker = " (duplicate)" if stored.is_duplicate else ""
        click.echo(f"{index}. {stored.analysed_on} by {stored.analysis.analyst}{marker}")
        if stored.was_computed:
            click.echo(
                f"   pure {stored.pure_seed_percent}  "
                f"other {stored.other_seed_percent}  "
                f"inert {stored.inert_percent}"
            )
        else:
            click.echo("   void, not worked out")

    computed = [stored for stored in analyses if stored.was_computed]
    if len(computed) >= 2:
        check = compare(
            computed[-2].pure_seed_percent,  # type: ignore[arg-type]
            computed[-1].pure_seed_percent,  # type: ignore[arg-type]
            chaffy=species.chaffy,
        )
        click.echo(check.explain())
