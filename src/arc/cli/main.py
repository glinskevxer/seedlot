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

import getpass
import sys
from datetime import date, datetime
from pathlib import Path

import click

from arc import STATION_CODE, STATION_NAME, __version__
from arc.cli.certificate_commands import certificate
from arc.cli.context import DEFAULT_DATABASE, Context, pass_context
from arc.cli.germination_commands import germination
from arc.cli.lot_commands import lot
from arc.cli.otherseed_commands import otherseed
from arc.cli.physical_commands import moisture, seedweight
from arc.cli.purity_commands import purity
from arc.cli.referee_commands import referee
from arc.cli.report_commands import report
from arc.cli.species_commands import species
from arc.cli.store_commands import store
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
    "--journal",
    type=click.Choice(["wal", "delete", "memory"]),
    default="wal",
    show_default=True,
    envvar="ARC_JOURNAL",
    help="SQLite journal mode. Use delete when the database is on a share.",
)
@click.option(
    "--sync",
    type=click.Choice(["full", "normal", "off"]),
    default="full",
    show_default=True,
    envvar="ARC_SYNC",
    help="How hard SQLite works to survive a power cut. Leave this alone.",
)
@click.option(
    "--operator",
    default=None,
    envvar="ARC_OPERATOR",
    help="Who is at the keyboard. Defaults to the account name.",
)
@click.option(
    "--today",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Record the work against this day rather than today.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    database: Path,
    quiet: bool,
    journal: str,
    sync: str,
    operator: str | None,
    today: datetime | None,
) -> None:
    """Analysis, reporting and certification for the seed testing station."""
    context = Context(
        database=database,
        quiet=quiet,
        today=today.date() if today is not None else date.today(),
        journal_mode=journal,
        synchronous=sync,
        operator=operator or _who(),
    )
    ctx.obj = context
    # Whatever the command does, the database is closed on the way out.
    ctx.call_on_close(context.close)


cli.add_command(species)
cli.add_command(lot)
cli.add_command(purity)
cli.add_command(germination)
cli.add_command(certificate)
cli.add_command(report)
cli.add_command(moisture)
cli.add_command(seedweight)
cli.add_command(otherseed)
cli.add_command(store)
cli.add_command(referee)


@cli.command()
@click.option(
    "--to",
    "destination",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("var/backups"),
    show_default=True,
    help="Directory the copy goes in.",
)
@click.option("--overwrite", is_flag=True, help="Replace today's copy if it is there.")
@pass_context
def backup(context: Context, destination: Path, overwrite: bool) -> None:
    """Take a checked copy of the database.

    Named for the day it was taken, so running it twice in a morning is a no
    op unless it is told otherwise, and a week of them sorts by name.
    """
    from arc.tools.backup import backup_to, dated_name

    opened = context.station()
    target = destination / dated_name(context.today)

    try:
        result = backup_to(opened.connection, target, overwrite=overwrite)
    except FileExistsError as already:
        click.echo(f"refused: {already}", err=True)
        click.echo("use --overwrite to replace it", err=True)
        raise SystemExit(2) from already

    click.echo(result.describe())
    if not result.verified:
        raise SystemExit(1)


@cli.command()
@pass_context
def doctor(context: Context) -> None:
    """Everything about this database that ought not to be true.

    Exits non zero when it finds something serious, so it can be the thing a
    Monday morning cron job runs and nobody reads unless it complains.
    """
    from arc.tools.doctor import Severity, examine, held_samples

    opened = context.station()
    findings = examine(opened.connection, on=context.today)

    context.say(f"{held_samples(opened.connection)} samples held")

    if not findings:
        click.echo("nothing to report")
        return

    for finding in findings:
        click.echo(str(finding))

    if any(finding.severity is Severity.SERIOUS for finding in findings):
        raise SystemExit(1)


@cli.command()
@pass_context
def guide(context: Context) -> None:
    """A job from start to finish, for whoever is new this week."""
    for line in (
        "A lot, start to finish:",
        "",
        "  arc lot book-in L-2025-0041 --species wheat --weight 24000 \\",
        "      --containers bag --container-count 480 \\",
        '      --merchant "Ravenscar Grain" --sealed-on 2025-03-04 --origin GB',
        "",
        "  arc purity record L-2025-0041 --working 120.0 --pure 118.2 \\",
        '      --other 0.9 --inert 0.9 --analyst "J. Whitfield"',
        "",
        "  arc germination record L-2025-0041 --tray 96,4,0,0,0 --tray 95,5,0,0,0 \\",
        "      --tray 97,3,0,0,0 --tray 96,4,0,0,0 \\",
        '      --set-down 2025-03-12 --final-count 2025-03-20 --analyst "J. Whitfield"',
        "",
        '  arc certificate issue L-2025-0041 --signed-by "A. Pearce"',
        "  arc certificate print GB-0214/2025/00001",
        "",
        "Then the sample goes in the store and is held against the certificate.",
        "  arc store show L-2025-0041      what is left, and until when",
        "  arc store due                   what has come out of its period",
        "",
        "Two commands about the station rather than about seed:",
        "  arc doctor                      what ought not to be true",
        "  arc backup                      a checked copy of the database",
        "",
        "Nothing here guesses. A command that will not accept what it was given",
        "says why and writes nothing.",
    ):
        click.echo(line)

    context.say("")
    context.say("Every command takes -h.")


@cli.command()
@click.option("--subject", default=None, help="Only entries about one thing.")
@click.option("--operator", "who", default=None, help="Only one person's entries.")
@click.option("--limit", type=int, default=20, show_default=True)
@pass_context
def journal(context: Context, subject: str | None, who: str | None, limit: int) -> None:
    """The day book: who did what, and when."""
    opened = context.station()

    if subject is not None:
        entries = opened.journal.for_subject(subject)
    elif who is not None:
        entries = opened.journal.by_operator(who)
    else:
        entries = opened.journal.latest(limit)

    if not entries:
        click.echo("nothing in the day book")
        return

    for entry in entries:
        click.echo(entry.describe())


@cli.command()
@pass_context
def station(context: Context) -> None:
    """Who this station is, as it appears on a certificate."""
    click.echo(f"{STATION_NAME} ({STATION_CODE})")
    context.say(f"database {context.database}")
    context.say(f"operator {context.operator}")


def _who() -> str:
    """Whoever is logged in, or a placeholder when even that fails.

    getuser reads the environment before it reads the password database, and
    on a machine with none of those set it raises rather than returning
    anything, which is not a reason for a command to fail.
    """
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


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
