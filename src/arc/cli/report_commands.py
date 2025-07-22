"""The registers, from the terminal.

Two of these print and one writes a file. The split is deliberate: the Monday
list is read on screen and thrown away, and the certificate register is emailed
to an auditor, so it goes to a file the person can attach without copying
anything out of a terminal by hand.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import click

from arc.cli.context import Context
from arc.reporting.registers import (
    certificate_register,
    merchant_register,
    other_seed_register,
    store_register,
    work_in_progress,
)
from arc.reporting.statistics import by_month, by_species, turnaround
from arc.species import register
from arc.workflow.schedule import expected_finish, overdue_on

__all__ = ["report"]


@click.group()
def report() -> None:
    """The registers the station has to be able to produce."""


def _deliver(context: Context, sheet: str, out: Path | None, what: str) -> None:
    """Sends a register to the terminal or to a file.

    Written once because it was written three times and two of them left out
    the newline argument. Without it Python translates the line endings on the
    way out, and the csv module has already put the ones the format wants in,
    so on Windows every row would end with two carriage returns.
    """
    if out is None:
        click.echo(sheet, nl=False)
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet, encoding="utf-8", newline="")

    rows = max(0, sheet.count("\r\n") - 1)
    context.say(f"wrote {rows} {what} to {out}")


@report.command("work")
@click.pass_obj
def work(context: Context) -> None:
    """What is open, oldest first. The Monday morning list."""
    station = context.station()
    items = work_in_progress(station.lots, station.certificates)

    if not items:
        click.echo("nothing open")
        return

    late = 0
    for item in items:
        lot = item.lot
        marker = "*" if item.is_waiting_on_the_bench else " "
        issued = (
            f"{item.certificates_issued} issued" if item.certificates_issued else "none issued"
        )

        # The date is on the Monday list rather than only on report due,
        # because the question the list is read to answer is what to do next,
        # and that is decided by what is closest to being late.
        expected = expected_finish(
            lot,
            register.require(lot.species_name),
            station.germination.for_lot(str(lot.reference)),
            booked_in_on=station.lots.booked_in_on(lot.reference) or context.today,
            on=context.today,
        )
        if expected.is_overdue_on(context.today):
            late += 1
            due = f"LATE since {expected.finish_on}"
        else:
            due = f"due {expected.finish_on}"

        click.echo(
            f"{marker} {lot.reference}  {lot.species_name:<22} "
            f"{lot.status.value:<10} {issued:<12} {due}"
        )

    context.say("")
    context.say("* on the bench now")
    if late:
        context.say(f"{late} past the date it should have been finished")


@report.command("merchant")
@click.argument("name")
@click.pass_obj
def merchant(context: Context, name: str) -> None:
    """One merchant's open lots and what has been issued on each."""
    station = context.station()
    found = merchant_register(station.lots, station.certificates, name)

    if not found:
        click.echo(f"nothing open for {name}")
        return

    for lot, certificates in found:
        click.echo(f"{lot.reference}  {lot.species_name}  {lot.declared_weight_kg} kg")
        for issued in certificates:
            state = " (withdrawn)" if issued.is_withdrawn else ""
            click.echo(f"    {issued.number}  {issued.issued_on}{state}")
        if not certificates:
            click.echo("    nothing issued yet")


@report.command("certificates")
@click.option(
    "--from",
    "start",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Defaults to the start of the current month.",
)
@click.option(
    "--to",
    "end",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Defaults to today.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write to a file rather than the terminal.",
)
@click.pass_obj
def certificates(context: Context, start: datetime, end: datetime, out: Path | None) -> None:
    """The certificate register, as the auditor asks for it."""
    station = context.station()

    last = end.date() if end is not None else context.today
    first = start.date() if start is not None else last.replace(day=1)

    if first > last:
        raise click.BadParameter("the register ends before it starts")

    sheet = certificate_register(station.certificates, start=first, end=last)

    _deliver(context, sheet, out, "certificates")


@report.command("expiring")
@click.option(
    "--within",
    type=int,
    default=60,
    show_default=True,
    help="Days ahead to look.",
)
@click.pass_obj
def expiring(context: Context, within: int) -> None:
    """Certificates whose germination figure is about to stop being quotable.

    A merchant holding a certificate whose germination has lapsed cannot sell
    on it, and the first they usually hear of it is a rejected consignment.
    """
    if within < 1:
        raise click.BadParameter("look at least one day ahead")

    station = context.station()
    horizon = context.today + timedelta(days=within)

    found = []
    for issued in station.certificates.issued_between(date(2000, 1, 1), context.today):
        expires = issued.germination_valid_until()
        if expires is None or issued.is_withdrawn:
            continue
        if context.today <= expires <= horizon:
            found.append((expires, issued))

    if not found:
        click.echo("nothing expiring")
        return

    for expires, issued in sorted(found, key=lambda pair: pair[0]):
        days = (expires - context.today).days
        click.echo(
            f"{issued.number}  {issued.lot_reference}  {issued.merchant}  "
            f"expires {expires} in {days} days"
        )


@report.command("searches")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write to a file rather than to the terminal.",
)
@click.pass_obj
def searches(context: Context, out: Path | None) -> None:
    """Every search for other species, as a spreadsheet."""
    station = context.station()
    _deliver(
        context,
        other_seed_register(station.lots, station.other_seed),
        out,
        "searches",
    )


@report.command("store")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write to a file rather than to the terminal.",
)
@click.pass_obj
def store_report(context: Context, out: Path | None) -> None:
    """What the sample store is holding, closest to its date first."""
    station = context.station()
    _deliver(
        context,
        store_register(station.retention, on=context.today),
        out,
        "samples",
    )


@report.command("year")
@click.option("--from", "start", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.option("--to", "end", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.pass_obj
def year(context: Context, start: datetime, end: datetime) -> None:
    """What the station did over a stretch of months."""
    station = context.station()
    first, last = start.date(), end.date()

    months = by_month(station.certificates, start=first, end=last)
    issued = sum(month.issued for month in months)

    click.echo(f"{issued} certificates issued between {first} and {last}")
    click.echo("")

    for month in months:
        taken_back = f"  ({month.withdrawn} withdrawn)" if month.withdrawn else ""
        click.echo(f"  {month.label}  {month.issued:>4}{taken_back}")

    click.echo("")
    for summary in by_species(station.certificates, start=first, end=last):
        germination = (
            f"mean germination {summary.mean_germination}"
            if summary.had_germinations
            else "no germinations"
        )
        click.echo(f"  {summary.species_name:<28}{summary.certificates:>4}   {germination}")

    took = turnaround(station.lots, station.certificates, start=first, end=last)
    if took is not None:
        click.echo("")
        click.echo(f"  {took.describe()}")


@report.command("due")
@click.option(
    "--late",
    is_flag=True,
    help="Only the ones that should already have been finished.",
)
@click.pass_obj
def due(context: Context, late: bool) -> None:
    """When the open lots should be finished."""
    station = context.station()

    expected = tuple(
        expected_finish(
            lot,
            register.require(lot.species_name),
            station.germination.for_lot(str(lot.reference)),
            booked_in_on=station.lots.booked_in_on(lot.reference) or context.today,
            on=context.today,
        )
        for lot in station.lots.open_lots()
    )

    if late:
        expected = overdue_on(expected, context.today)
        if not expected:
            click.echo("nothing is late")
            return
    elif not expected:
        click.echo("nothing is open")
        return

    for item in sorted(expected, key=lambda entry: entry.finish_on):
        click.echo(item.describe(context.today))
