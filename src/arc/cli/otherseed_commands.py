"""Recording a search for other species, and reading the counts back.

The findings arrive as repeated options rather than as one string, because a
botanical name has a space in it and any single argument holding several of
them needs a separator that no species name contains. There is no such
separator worth relying on, so each finding is its own option.
"""

from __future__ import annotations

import click

from arc.cli.context import Context
from arc.cli.station import weight_option
from arc.otherseed.model import Finding, OtherSeedSearch, SearchKind
from arc.otherseed.rules import check_search, required_weight_g
from arc.otherseed.tolerance import compare
from arc.species import register

__all__ = ["otherseed"]


def _findings(raw: tuple[str, ...]) -> tuple[Finding, ...]:
    """Reads --found options, each of them a species name and a count."""
    parsed: list[Finding] = []
    for item in raw:
        name, separator, count = item.rpartition("=")
        if not separator or not name.strip():
            raise click.BadParameter(
                f"{item!r} should be a species and a count, like 'Avena fatua=4'",
                param_hint="--found",
            )
        try:
            parsed.append(Finding(name.strip(), int(count)))
        except ValueError as error:
            raise click.BadParameter(str(error), param_hint="--found") from error
    return tuple(parsed)


@click.group()
def otherseed() -> None:
    """Seeds of other species, counted rather than weighed."""


@otherseed.command("needed")
@click.argument("species_name")
@click.option(
    "--kind",
    type=click.Choice([kind.value for kind in SearchKind]),
    default=SearchKind.COMPLETE.value,
    show_default=True,
)
def needed(species_name: str, kind: str) -> None:
    """How much seed a search of this kind has to go through."""
    species = register.require(species_name)
    weight = required_weight_g(species, SearchKind(kind))

    click.echo(f"{species.botanical_name} ({species.common_name})")
    click.echo(f"  {kind} search  {weight} g")
    click.echo(f"  purity working sample  {species.purity_working_sample_g} g")


@otherseed.command("record")
@click.argument("reference")
@click.option("--weight", "weight_g", required=True, help="Grams actually searched.")
@click.option(
    "--kind",
    type=click.Choice([kind.value for kind in SearchKind]),
    default=SearchKind.COMPLETE.value,
    show_default=True,
)
@click.option(
    "--found",
    multiple=True,
    help="A species and a count, like 'Avena fatua=4'. Repeat for each one.",
)
@click.option(
    "--seek",
    multiple=True,
    help="A species the search was asked to look for. Repeat for each one.",
)
@click.option("--analyst", required=True)
@click.pass_obj
def record(
    context: Context,
    reference: str,
    weight_g: str,
    kind: str,
    found: tuple[str, ...],
    seek: tuple[str, ...],
    analyst: str,
) -> None:
    """Record one search through one working sample."""
    station = context.station()
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)

    search = OtherSeedSearch(
        species_name=species.botanical_name,
        kind=SearchKind(kind),
        weight_examined_g=weight_option(weight_g),
        findings=_findings(found),
        sought=tuple(name.strip() for name in seek),
        analyst=analyst,
    )

    broken = check_search(search, species)
    if broken:
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2)

    station.other_seed.record(reference, search, searched_on=context.today)

    context.record(station, "searched for other seed in", reference, search.describe())

    context.say(f"recorded against {reference}")
    click.echo(search.describe())

    for finding in search.findings:
        if finding.count:
            rate = search.rate_per_kg(finding.species_name)
            click.echo(f"  {finding.species_name}  {rate} per kg")


@otherseed.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """Every search against one lot."""
    station = context.station()
    station.lots.require(reference)
    searches = station.other_seed.for_lot(reference)

    if not searches:
        click.echo("nothing searched yet")
        return

    for index, stored in enumerate(searches, start=1):
        click.echo(f"{index}. {stored.searched_on} by {stored.search.analyst}")
        click.echo(f"   {stored.search.describe()}")
        if stored.search.sought:
            click.echo(f"   looked for {', '.join(stored.search.sought)}")


@otherseed.command("compare")
@click.argument("reference")
@click.argument("species_name")
@click.pass_obj
def compare_counts(context: Context, reference: str, species_name: str) -> None:
    """Whether two searches of one lot agree about one species."""
    station = context.station()
    station.lots.require(reference)
    counts = station.other_seed.counts_of(reference, species_name)

    if len(counts) < 2:
        click.echo(f"only {len(counts)} search covered {species_name}", err=True)
        raise SystemExit(2)

    result = compare(counts[-2], counts[-1])
    click.echo(result.explain())

    if not result.within_tolerance:
        raise SystemExit(1)
