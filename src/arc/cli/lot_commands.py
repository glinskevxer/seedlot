"""Booking lots in and looking at them, from the terminal."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.errors import RuleBroken
from arc.lots.model import ContainerKind, LotReference, SeedLot
from arc.workflow.booking import book_in, split_advice

__all__ = ["lot"]


def _weight(raw: str) -> Decimal:
    return weight_option(raw)


@click.group()
def lot() -> None:
    """Seed lots as they come in and go out."""


@lot.command("book-in")
@click.argument("reference")
@click.option("--species", required=True, help="Botanical or common name.")
@click.option("--weight", "weight_kg", required=True, help="Declared weight in kilograms.")
@click.option(
    "--containers",
    type=click.Choice([kind.value for kind in ContainerKind]),
    default=ContainerKind.BAG.value,
    show_default=True,
)
@click.option("--container-count", type=int, default=0, help="Zero for bulk.")
@click.option("--merchant", required=True)
@click.option("--sealed-on", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.option("--origin", required=True, help="Two letter country code.")
@click.pass_obj
def book_in_command(
    context: Context,
    reference: str,
    species: str,
    weight_kg: str,
    containers: str,
    container_count: int,
    merchant: str,
    sealed_on: datetime,
    origin: str,
) -> None:
    """Accept a lot and print the sampling docket."""
    incoming = SeedLot(
        reference=LotReference.parse(reference),
        species_name=species,
        declared_weight_kg=_weight(weight_kg),
        container_kind=ContainerKind(containers),
        container_count=container_count,
        merchant=merchant,
        sealed_on=sealed_on.date(),
        origin_country=origin.upper(),
    )

    lots = context.station().lots
    try:
        booked = book_in(incoming, lots, on=context.today)
    except RuleBroken as refused:
        for rule in refused.rules:
            click.echo(f"refused: {rule.detail}", err=True)
        needed, advice = split_advice(incoming)
        if needed > 1:
            click.echo(advice, err=True)
        raise SystemExit(2) from refused

    context.say(f"booked in {booked.reference}")
    for line in booked.plan.docket_lines():
        click.echo(line)


@lot.command("show")
@click.argument("reference")
@click.pass_obj
def show_lot(context: Context, reference: str) -> None:
    """Everything the station knows about one lot."""
    lots = context.station().lots
    found = lots.require(reference)

    click.echo(f"{found.reference} {found.species_name}")
    click.echo(f"  weight      {found.declared_weight_kg} kg")
    click.echo(f"  put up as   {found.container_kind.value}")
    if found.container_kind.is_containerised:
        click.echo(f"  containers  {found.container_count}")
    click.echo(f"  merchant    {found.merchant}")
    click.echo(f"  sealed on   {found.sealed_on}")
    click.echo(f"  origin      {found.origin_country}")
    click.echo(f"  status      {found.status.value}")
    if found.is_sublot:
        click.echo(f"  sublot of   {found.sublot_of}")

    sublots = lots.sublots_of(found.reference)
    if sublots:
        click.echo(f"  split into  {', '.join(str(s.reference) for s in sublots)}")


@lot.command("list")
@click.option("--species", help="Only lots of one species.")
@click.pass_obj
def list_lots(context: Context, species: str | None) -> None:
    """The lots still open, oldest first."""
    lots = context.station().lots
    found = lots.for_species(species) if species else lots.open_lots()

    if not found:
        click.echo("nothing open")
        return

    for item in found:
        click.echo(
            f"{item.reference}  {item.species_name:<22} "
            f"{item.declared_weight_kg:>9} kg  {item.status.value}"
        )
