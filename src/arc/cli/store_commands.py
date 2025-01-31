"""The sample store, from the terminal.

Whoever is in the store has a trolley and a printed list, and comes back to
type in what they did. So the commands are the four things that happen to a
jar: look at it, take some out, throw it away, and find out which ones are
past their date.
"""

from __future__ import annotations

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.retention.model import Determination, DisposalReason
from arc.retention.rules import check_disposal, check_repeat, needed_for, possible_from
from arc.species import register

__all__ = ["store"]


@click.group()
def store() -> None:
    """Retained samples: what is held, and what is left of it."""


@store.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """One jar: what is in it, how long it is held, what it could still do."""
    station = context.station()
    sample = station.retention.require(reference)
    species = register.require(sample.species_name)

    click.echo(f"{sample.lot_reference} {sample.species_name}")
    click.echo(f"  {sample.describe(context.today)}")
    click.echo(f"  held from   {sample.held_from}")
    click.echo(f"  hold until  {sample.hold_until}")

    if not sample.is_held:
        return

    still = possible_from(sample, species)
    if not still:
        click.echo("  nothing can be repeated from what is left")
        return

    click.echo("  could still cover, one at a time:")
    for determination in still:
        click.echo(f"    {determination.value}  {needed_for(determination, species)} g")


@store.command("draw")
@click.argument("reference")
@click.option(
    "--for",
    "determination",
    type=click.Choice([item.value for item in Determination]),
    required=True,
    help="Which repeat the seed is coming out for.",
)
@click.option("--analyst", required=True)
@click.option(
    "--weight",
    "weight_g",
    default=None,
    help="Grams to take. Defaults to the working sample for the determination.",
)
@click.pass_obj
def draw(
    context: Context,
    reference: str,
    determination: str,
    analyst: str,
    weight_g: str | None,
) -> None:
    """Take seed out of a jar for a repeat test."""
    station = context.station()
    sample = station.retention.require(reference)
    species = register.require(sample.species_name)
    wanted = Determination(determination)

    broken = check_repeat(sample, wanted, species, on=context.today)
    if broken:
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2)

    taking = needed_for(wanted, species) if weight_g is None else weight_option(weight_g)
    left = station.retention.draw(reference, wanted, taking, on=context.today, analyst=analyst)

    context.say(f"drew {taking} g for a {wanted.value}")
    click.echo(f"{left.remaining_g} g left")


@store.command("dispose")
@click.argument("reference")
@click.option(
    "--reason",
    type=click.Choice([reason.value for reason in DisposalReason]),
    default=DisposalReason.PERIOD_EXPIRED.value,
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    help="Throw it out even though the retention period is still running.",
)
@click.pass_obj
def dispose(context: Context, reference: str, reason: str, force: bool) -> None:
    """Record that a jar has gone."""
    station = context.station()
    sample = station.retention.require(reference)
    why = DisposalReason(reason)

    broken = check_disposal(sample, on=context.today)
    blocking = [rule for rule in broken if rule.code != "SAMPLE_STILL_IN_ITS_PERIOD"]

    if blocking or (broken and not force):
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        if not blocking:
            click.echo("use --force if it has to go anyway", err=True)
        raise SystemExit(2)

    if broken and force and why.is_ordinary:
        # It cannot have expired, because the period is still running.
        raise click.BadParameter(
            "the period has not run out, so say why it is going",
            param_hint="--reason",
        )

    station.retention.dispose(reference, on=context.today, reason=why)
    context.say(f"{reference} disposed, {why.value}")


@store.command("due")
@click.pass_obj
def due(context: Context) -> None:
    """Every jar whose retention period has run out."""
    station = context.station()
    overdue = station.retention.due_for_disposal(context.today)

    if not overdue:
        click.echo("nothing is due")
        return

    for sample in overdue:
        click.echo(sample.describe(context.today))


@store.command("list")
@click.pass_obj
def list_held(context: Context) -> None:
    """Everything the store is holding, oldest first."""
    station = context.station()
    held = station.retention.held()

    if not held:
        click.echo("the store is empty")
        return

    for sample in held:
        click.echo(sample.describe(context.today))
