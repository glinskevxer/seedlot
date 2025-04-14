"""Comparing a result with another laboratory's, from the terminal.

The merchant is usually on the phone while this is being typed, which is why
the command prints the comparison in full rather than a verdict. Whoever is
holding the phone needs the two numbers and the allowance, in that order,
because that is the order the argument goes in.
"""

from __future__ import annotations

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.referee.between_labs import compare_germination, compare_purity
from arc.retention.model import Determination
from arc.species import register

__all__ = ["referee"]


@click.group()
def referee() -> None:
    """Second opinions from another laboratory."""


@referee.command("compare")
@click.argument("reference")
@click.option("--certificate", required=True, help="The certificate being disputed.")
@click.option(
    "--for",
    "determination",
    type=click.Choice(["purity", "germination"]),
    required=True,
)
@click.option("--theirs", required=True, help="What the other laboratory reported.")
@click.option("--laboratory", required=True, help="Who did the second test.")
@click.option("--raised-by", required=True, help="Who asked for it.")
@click.pass_obj
def compare(
    context: Context,
    reference: str,
    certificate: str,
    determination: str,
    theirs: str,
    laboratory: str,
    raised_by: str,
) -> None:
    """Hold our result up against another laboratory's and record the outcome."""
    station = context.station()
    issued = station.certificates.require(certificate)
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)
    wanted = Determination(determination)

    if issued.lot_reference != str(lot.reference):
        raise click.BadParameter(
            f"{certificate} was issued against {issued.lot_reference}, not {reference}",
            param_hint="--certificate",
        )

    if wanted is Determination.GERMINATION:
        ours = issued.results.germination_percent
        if ours is None:
            click.echo(f"refused: {certificate} carries no germination", err=True)
            raise SystemExit(2)
        comparison = compare_germination(ours, int(theirs))
    else:
        pure = issued.results.pure_seed
        if pure is None:
            click.echo(f"refused: {certificate} carries no purity", err=True)
            raise SystemExit(2)
        comparison = compare_purity(
            pure.value, weight_option(theirs, "percentage"), chaffy=species.chaffy
        )

    station.referee.record(
        str(lot.reference),
        certificate,
        wanted,
        comparison,
        other_laboratory=laboratory,
        raised_by=raised_by,
        on=context.today,
    )

    context.record(
        station,
        "compared with another laboratory for",
        str(lot.reference),
        f"{laboratory}: {comparison.verdict.value}",
    )

    click.echo(comparison.explain())
    if comparison.verdict.needs_a_third_opinion:
        raise SystemExit(1)


@referee.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """Every comparison made against one lot."""
    station = context.station()
    station.lots.require(reference)
    comparisons = station.referee.for_lot(reference)

    if not comparisons:
        click.echo("nothing has been disputed")
        return

    for index, stored in enumerate(comparisons, start=1):
        click.echo(f"{index}. {stored.describe()}")
        click.echo(f"   raised by {stored.raised_by} against {stored.certificate_number}")


@referee.command("disputed")
@click.pass_obj
def disputed(context: Context) -> None:
    """Every comparison that did not agree, newest first."""
    station = context.station()
    open_disputes = station.referee.disputed()

    if not open_disputes:
        click.echo("nothing outstanding")
        return

    for stored in open_disputes:
        click.echo(f"{stored.lot_reference}  {stored.describe()}")
