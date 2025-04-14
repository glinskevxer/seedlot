"""Issuing and looking up certificates."""

from __future__ import annotations

from pathlib import Path

import click

from arc import STATION_CODE, STATION_NAME
from arc.certificates.model import Certificate, CertificateKind
from arc.cli.context import Context
from arc.errors import RuleBroken
from arc.reporting.certificate_form import render_many
from arc.workflow.issuing import gather, issue

__all__ = ["certificate"]

_KINDS = {
    "orange": CertificateKind.ORANGE_INTERNATIONAL,
    "blue": CertificateKind.BLUE_INTERNATIONAL,
    "green": CertificateKind.GREEN_ANALYSIS,
}


@click.group()
def certificate() -> None:
    """Certificates: the only thing that leaves the building."""


@certificate.command("check")
@click.argument("reference")
@click.pass_obj
def check(context: Context, reference: str) -> None:
    """What the station has on a lot, and whether it is enough to certify."""
    station = context.station()
    lot = station.lots.require(reference)

    gathered = gather(
        reference,
        lot.species_name,
        purity=station.purity,
        germination=station.germination,
        moisture=station.moisture,
        seed_weight=station.seed_weight,
    )

    done = gathered.results.determinations()
    click.echo(f"{reference} {lot.species_name}")
    click.echo(f"  determined  {', '.join(done) if done else 'nothing yet'}")

    if gathered.results.has_purity:
        click.echo(f"  pure seed   {gathered.results.pure_seed}")
    if gathered.results.has_germination:
        click.echo(f"  germination {gathered.results.germination_percent} percent")
    if gathered.results.moisture_percent is not None:
        click.echo(f"  moisture    {gathered.results.moisture_percent} percent")
    if gathered.results.thousand_seed_weight_g is not None:
        click.echo(f"  seed weight {gathered.results.thousand_seed_weight_g} g per thousand")

    if gathered.is_ready:
        click.echo("  ready to certify")
    else:
        for rule in gathered.problems:
            click.echo(f"  not ready: {rule.detail}")


@certificate.command("issue")
@click.argument("reference")
@click.option(
    "--kind",
    type=click.Choice(sorted(_KINDS)),
    default="orange",
    show_default=True,
)
@click.option("--signed-by", required=True)
@click.pass_obj
def issue_command(context: Context, reference: str, kind: str, signed_by: str) -> None:
    """Issue a certificate for a lot."""
    station = context.station()

    try:
        issued = issue(
            reference,
            _KINDS[kind],
            signed_by=signed_by,
            on=context.today,
            lots=station.lots,
            purity=station.purity,
            germination=station.germination,
            certificates=station.certificates,
            retention=station.retention,
            moisture=station.moisture,
            seed_weight=station.seed_weight,
        )
    except RuleBroken as refused:
        for rule in refused.rules:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2) from refused

    context.record(
        station, "issued", str(issued.number), f"against {reference}, signed {signed_by}"
    )
    context.say(f"issued against {reference}")
    click.echo(str(issued.number))


@certificate.command("show")
@click.argument("number")
@click.pass_obj
def show(context: Context, number: str) -> None:
    """One certificate, as it reads."""
    station = context.station()
    found = station.certificates.require(number)
    results = found.results

    click.echo(str(found.number))
    click.echo(f"  kind        {found.kind.value}")
    click.echo(f"  lot         {found.lot_reference}")
    click.echo(f"  species     {found.species_name}")
    click.echo(f"  merchant    {found.merchant}")
    click.echo(f"  weight      {found.lot_weight_kg} kg")
    click.echo(f"  origin      {found.origin_country}")
    click.echo(f"  issued      {found.issued_on} by {found.signed_by}")

    if results.has_purity:
        click.echo(
            f"  purity      pure {results.pure_seed}  "
            f"other {results.other_seed}  inert {results.inert_matter}"
        )
    if results.has_germination:
        valid_until = found.germination_valid_until()
        click.echo(
            f"  germination {results.germination_percent} percent, quotable to {valid_until}"
        )
    if results.moisture_percent is not None:
        click.echo(f"  moisture    {results.moisture_percent} percent")
    if results.thousand_seed_weight_g is not None:
        click.echo(f"  seed weight {results.thousand_seed_weight_g} g per thousand")

    if found.is_replacement:
        click.echo(f"  supersedes  {found.supersedes}")
    if found.is_withdrawn:
        click.echo(f"  withdrawn   {found.withdrawn_on}")


@certificate.command("withdraw")
@click.argument("number")
@click.pass_obj
def withdraw(context: Context, number: str) -> None:
    """Withdraw a certificate. The row stays; somebody holds a copy."""
    station = context.station()
    station.certificates.withdraw(number, on=context.today)
    context.say(f"withdrawn {number}")


@certificate.command("print")
@click.argument("number", required=False)
@click.option("--lot", "lot_reference", default=None, help="Every certificate on a lot.")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write to a file rather than to the terminal.",
)
@click.pass_obj
def print_form(
    context: Context,
    number: str | None,
    lot_reference: str | None,
    out: Path | None,
) -> None:
    """Print a certificate onto the form.

    Either one number, or every certificate on one lot. Printing a lot's whole
    history is what the station does when a merchant disputes something, and
    the run comes out separated by form feeds so the stationery advances.
    """
    if (number is None) == (lot_reference is None):
        raise click.UsageError("give either a certificate number or --lot, not both")

    station = context.station()

    wanted: tuple[Certificate, ...]
    if number is not None:
        wanted = (station.certificates.require(number),)
    else:
        station.lots.require(str(lot_reference))
        wanted = station.certificates.for_lot(str(lot_reference))
        if not wanted:
            click.echo("nothing has been issued on that lot", err=True)
            raise SystemExit(2)

    form = render_many(wanted, station_name=STATION_NAME, station_code=STATION_CODE)

    if out is None:
        click.echo(form)
        return

    out.write_text(form, encoding="utf-8")
    context.say(f"{len(wanted)} written to {out}")
