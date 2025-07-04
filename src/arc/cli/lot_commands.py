"""Booking lots in and looking at them, from the terminal."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.errors import RuleBroken
from arc.importing.merchant_csv import parse
from arc.lots.model import ContainerKind, LotReference, SeedLot
from arc.workflow.booking import book_in, split_advice
from arc.workflow.splitting import split

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

    station = context.station()
    try:
        booked = book_in(incoming, station.lots, on=context.today)
    except RuleBroken as refused:
        for rule in refused.rules:
            click.echo(f"refused: {rule.detail}", err=True)
        needed, advice = split_advice(incoming)
        if needed > 1:
            click.echo(advice, err=True)
        raise SystemExit(2) from refused

    context.record(
        station,
        "booked in",
        str(booked.reference),
        f"{booked.lot.declared_weight_kg} kg of {booked.lot.species_name}",
    )

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


@lot.command("import")
@click.argument("path", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--merchant", required=True, help="Whose list this is.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Say what would happen and write nothing.",
)
@click.pass_obj
def import_lots(context: Context, path: Path, merchant: str, dry_run: bool) -> None:
    """Book in a merchant's list of lots.

    Two kinds of thing can be wrong and they are reported separately. A row the
    file cannot turn into a lot at all is the merchant's to fix. A lot the
    station will not accept, because it is over the maximum weight for the
    species, is a conversation about splitting it, and the advice for that is
    printed with it.
    """
    read = parse(path.read_text(encoding="utf-8"), merchant)

    for problem in read.problems:
        click.echo(str(problem), err=True)

    if not read.lots:
        click.echo(read.summary(), err=True)
        raise SystemExit(2)

    station = context.station()
    booked = 0
    refused = 0

    if dry_run:
        # The connection is in autocommit, so there is nothing for a rollback
        # to undo unless a transaction is opened first. Without this the dry
        # run books everything in and then says it did not.
        station.connection.execute("begin")

    for incoming in read.lots:
        try:
            accepted = book_in(incoming, station.lots, on=context.today)
        except RuleBroken as broken:
            refused += 1
            for rule in broken.rules:
                click.echo(f"{incoming.reference}: {rule.detail}", err=True)
            needed, advice = split_advice(incoming)
            if needed > 1:
                click.echo(f"{incoming.reference}: {advice}", err=True)
            continue

        booked += 1
        if not dry_run:
            context.say(f"booked in {accepted.reference}")

    if dry_run:
        station.connection.execute("rollback")
        click.echo(f"dry run: {booked} would be booked in, {refused} refused")
        return

    click.echo(f"{booked} booked in, {refused} refused, {len(read.problems)} rows to fix")

    if refused or read.problems:
        raise SystemExit(1)


@lot.command("split")
@click.argument("reference")
@click.option("--species", required=True, help="Botanical or common name.")
@click.option("--weight", "weight_kg", required=True, help="The whole consignment, kg.")
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
@click.option(
    "--sublots-from",
    type=int,
    required=True,
    help="The serial the first sublot takes. They run on from there.",
)
@click.pass_obj
def split_lot(
    context: Context,
    reference: str,
    species: str,
    weight_kg: str,
    containers: str,
    container_count: int,
    merchant: str,
    sealed_on: datetime,
    origin: str,
    sublots_from: int,
) -> None:
    """Split a consignment too heavy to be one lot and book the sublots in.

    The consignment itself is recorded closed. It is not something anybody can
    test, and without it the shelf holds three references with nothing saying
    they came off the same lorry.
    """
    consignment = SeedLot(
        reference=LotReference.parse(reference),
        species_name=species,
        declared_weight_kg=_weight(weight_kg),
        container_kind=ContainerKind(containers),
        container_count=container_count,
        merchant=merchant,
        sealed_on=sealed_on.date(),
        origin_country=origin.upper(),
    )

    station = context.station()
    try:
        done = split(
            consignment,
            station.lots,
            starting_serial=sublots_from,
            on=context.today,
        )
    except RuleBroken as refused:
        for rule in refused.rules:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2) from refused

    context.record(
        station,
        "split",
        str(consignment.reference),
        f"into {done.count} sublots",
    )

    context.say(done.describe())
    for sublot in done.sublots:
        click.echo(f"{sublot.reference}  {sublot.declared_weight_kg} kg")
