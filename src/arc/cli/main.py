"""The command line, which is how the station actually uses this.

There is no web front end and there is not going to be one. Four analysts share
one room, the worksheets are on paper, and what they need is something that
answers a question in one line without leaving the terminal they already have
open.

Every command prints something a person can read. Nothing prints a traceback: a
refusal is a message and a non zero exit code, because the analyst who typed it
is not the person who would fix a stack trace.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import click

from arc import STATION_CODE, STATION_NAME, __version__
from arc.cli.certificate_commands import certificate
from arc.cli.context import DEFAULT_DATABASE, Context, pass_context
from arc.cli.germination_commands import germination
from arc.cli.lot_commands import lot
from arc.cli.physical_commands import moisture, seedweight
from arc.cli.purity_commands import purity
from arc.cli.report_commands import report
from arc.cli.species_commands import species
from arc.errors import ArcError, NotFound, RuleBroken

__all__ = ["cli", "main"]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="arc")
@click.option(
    "--database",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_DATABASE,
    show_default=True,
    envvar="ARC_DATABASE",
    help="Where the station's database lives.",
)
@click.option("--quiet", "-q", is_flag=True, help="Print results and nothing else.")
@click.option(
    "--today",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Record the work against this day rather than today.",
)
@click.pass_context
def cli(ctx: click.Context, database: Path, quiet: bool, today: datetime | None) -> None:
    """Analysis, reporting and certification for the seed testing station."""
    ctx.obj = Context(
        database=database,
        quiet=quiet,
        today=today.date() if today is not None else date.today(),
    )


cli.add_command(species)
cli.add_command(lot)
cli.add_command(purity)
cli.add_command(germination)
cli.add_command(certificate)
cli.add_command(report)
cli.add_command(moisture)
cli.add_command(seedweight)


@cli.command()
@pass_context
def station(context: Context) -> None:
    """Who this station is, as it appears on a certificate."""
    click.echo(f"{STATION_NAME} ({STATION_CODE})")
    context.say(f"database {context.database}")


def main(argv: list[str] | None = None) -> int:
    """Runs the command line and turns a refusal into an exit code.

    Click would print a traceback for anything it does not recognise, which is
    no use to somebody standing at a bench. The four shapes the station raises
    are turned into a sentence and a code instead.
    """
    try:
        cli.main(args=argv, standalone_mode=False)
    except RuleBroken as refused:
        for rule in refused.rules:
            click.echo(f"refused: {rule.detail}", err=True)
        return 2
    except NotFound as missing:
        click.echo(f"not found: {missing}", err=True)
        return 3
    except ArcError as error:
        click.echo(f"error: {error}", err=True)
        return 4
    except click.ClickException as error:
        error.show()
        return error.exit_code
    except click.Abort:
        click.echo("stopped", err=True)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
