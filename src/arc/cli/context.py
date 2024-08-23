"""What every command is handed, and where the database lives.

This sits in its own module so the command modules can name the type they are
given without importing the module that imports them. Putting it in main meant
every command file had to take its context untyped, and an untyped parameter
that is passed to everything hides exactly the mistakes a type checker is there
to find.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

__all__ = ["Context", "DEFAULT_DATABASE", "pass_context"]

DEFAULT_DATABASE = Path("var/arc.sqlite3")


class Context:
    """What every command needs, put together once at the top."""

    def __init__(self, database: Path, quiet: bool, today: date) -> None:
        self.database = database
        self.quiet = quiet
        #: The day the work is being recorded against. Normally today, but the
        #: bench sheets are sometimes typed up the next morning and the dates
        #: on them have to be the dates the work was actually done.
        self.today = today

    def say(self, message: str) -> None:
        """Prints progress, which --quiet turns off."""
        if not self.quiet:
            click.echo(message)

    def warn(self, message: str) -> None:
        """Prints a problem, which --quiet does not turn off."""
        click.echo(message, err=True)


pass_context = click.make_pass_decorator(Context)
