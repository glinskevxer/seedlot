"""Looking things up in the species register from the terminal.

The command an analyst runs most often, because the working sample size and the
germination method are on the handbook page and the handbook is across the room.
"""

from __future__ import annotations

import click

from arc.errors import NotFound
from arc.species import register
from arc.species.model import SeedClass

__all__ = ["species"]


@click.group()
def species() -> None:
    """What the handbook says about a species."""


@species.command("list")
@click.option(
    "--seed-class",
    type=click.Choice([member.value for member in SeedClass], case_sensitive=False),
    help="Only species in one class.",
)
@click.option("--chaffy", is_flag=True, help="Only the awkward ones.")
def list_species(seed_class: str | None, chaffy: bool) -> None:
    """Every species the station is accredited for."""
    entries = list(register)

    if seed_class is not None:
        wanted = SeedClass(seed_class.lower())
        entries = [entry for entry in entries if entry.seed_class is wanted]
    if chaffy:
        entries = [entry for entry in entries if entry.chaffy]

    if not entries:
        click.echo("nothing matches")
        return

    width = max(len(entry.botanical_name) for entry in entries)
    for entry in sorted(entries, key=lambda item: item.botanical_name):
        click.echo(f"{entry.botanical_name:<{width}}  {entry.common_name}")


@species.command("show")
@click.argument("name")
def show_species(name: str) -> None:
    """Everything the handbook says about one species."""
    found = register.find(name)
    if found is None:
        suggestions = register.suggest(name)
        if suggestions:
            click.echo(f"no species called {name!r}, did you mean:", err=True)
            for suggestion in suggestions:
                click.echo(f"  {suggestion}", err=True)
        raise NotFound("species", name)

    germination = found.germination
    moisture = found.moisture

    click.echo(f"{found.botanical_name} ({found.common_name})")
    click.echo(f"  class                 {found.seed_class.label}")
    click.echo(f"  maximum lot           {found.max_lot_kg} kg")
    click.echo(f"  submitted sample      {found.submitted_sample_g} g")
    click.echo(f"  purity working sample {found.purity_working_sample_g} g")
    click.echo(f"  other seed sample     {found.other_seed_working_sample_g} g")
    click.echo(f"  chaffy                {'yes' if found.chaffy else 'no'}")
    click.echo(
        f"  germination           {germination.substrate.code} at {germination.temperature}, "
        f"count day {germination.first_count_day} to {germination.final_count_day}"
    )
    if germination.needs_prechill:
        click.echo(f"  prechill              {germination.prechill_days} days")
    click.echo(f"  moisture              {moisture.oven.value}, {moisture.grinding.value}")
    if found.aliases:
        click.echo(f"  also called           {', '.join(found.aliases)}")
