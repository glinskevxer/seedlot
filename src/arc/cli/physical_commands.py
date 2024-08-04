"""Recording moisture and thousand seed weight from the bench.

Both take the raw weighings rather than a percentage, for the same reason the
germination command takes trays rather than a germination: the station records
what was on the balance and does the arithmetic itself.
"""

from __future__ import annotations

import click

from arc.cli.station import open_station, weight_option
from arc.moisture.determination import (
    Weighing,
    check_duplicates,
    combine_stages,
    moisture_of,
    needs_predrying,
)
from arc.species import register
from arc.storage.physical import MoistureStage
from arc.weight.thousand_seed import check as check_seed_weight
from arc.weight.thousand_seed import measure

__all__ = ["moisture", "seedweight"]


@click.group()
def moisture() -> None:
    """Moisture content: three weighings, sometimes six."""


@moisture.command("record")
@click.argument("reference")
@click.option("--container", required=True, help="The empty container, in grams.")
@click.option("--wet", required=True, help="Container and sample, before the oven.")
@click.option("--dry", required=True, help="Container and sample, after the oven.")
@click.option("--analyst", required=True)
@click.option(
    "--stage",
    type=click.Choice([stage.value for stage in MoistureStage]),
    default=MoistureStage.SINGLE.value,
    show_default=True,
    help="Which part of a two stage determination this is.",
)
@click.option(
    "--predry-percent",
    default=None,
    help="The first stage figure, when recording a second stage.",
)
@click.pass_obj
def record_moisture(
    context,
    reference: str,
    container: str,
    wet: str,
    dry: str,
    analyst: str,
    stage: str,
    predry_percent: str | None,
) -> None:
    """Record one moisture weighing and say what it comes to."""
    station = open_station(context.database)
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)

    weighing = Weighing(
        container_g=weight_option(container),
        with_sample_g=weight_option(wet),
        after_drying_g=weight_option(dry),
    )
    result = moisture_of(weighing)
    which = MoistureStage(stage)

    combined = None
    if which is MoistureStage.SECOND:
        if predry_percent is None:
            raise click.BadParameter(
                "a second stage needs the first stage figure to combine with",
                param_hint="--predry-percent",
            )
        combined = combine_stages(weight_option(predry_percent, "percentage"), result.percent)

    station.moisture.record(
        reference,
        weighing,
        result,
        analyst=analyst,
        determined_on=context.today,
        stage=which,
        combined_percent=combined,
    )

    context.say(f"recorded against {reference}")
    click.echo(f"moisture {result.percent} percent")

    if combined is not None:
        click.echo(f"combined {combined} percent")
    elif needs_predrying(result, species):
        click.echo(
            "over seventeen percent, so predry the sample and record a second stage",
            err=True,
        )


@moisture.command("show")
@click.argument("reference")
@click.pass_obj
def show_moisture(context, reference: str) -> None:
    """Every moisture weighing on a lot, and what would be reported."""
    station = open_station(context.database)
    station.lots.require(reference)
    stored = station.moisture.for_lot(reference)

    if not stored:
        click.echo("nothing determined yet")
        return

    for index, row in enumerate(stored, start=1):
        click.echo(
            f"{index}. {row.determined_on} {row.stage.value:<7} "
            f"{row.result.percent} percent by {row.analyst}"
        )

    singles = [row for row in stored if row.stage is MoistureStage.SINGLE]
    if len(singles) >= 2:
        broken = check_duplicates(singles[-2].result, singles[-1].result)
        for rule in broken:
            click.echo(rule.detail)
        if not broken:
            click.echo("the duplicates agree")

    reportable = station.moisture.reportable_for_lot(reference)
    click.echo(f"reporting {reportable} percent")


@click.group()
def seedweight() -> None:
    """Thousand seed weight: eight hundred seeds, weighed in eight lots."""


@seedweight.command("record")
@click.argument("reference")
@click.option(
    "--replicate",
    "replicates",
    multiple=True,
    required=True,
    help="One per hundred seed replicate, in grams. Eight of them.",
)
@click.option("--analyst", required=True)
@click.pass_obj
def record_seed_weight(
    context, reference: str, replicates: tuple[str, ...], analyst: str
) -> None:
    """Record a thousand seed weight determination."""
    station = open_station(context.database)
    lot = station.lots.require(reference)
    species = register.require(lot.species_name)

    weights = tuple(weight_option(raw) for raw in replicates)
    determination = measure(weights, species)

    station.seed_weight.record(
        reference, determination, analyst=analyst, determined_on=context.today
    )

    context.say(f"recorded against {reference}")
    click.echo(f"{determination.grams_per_thousand} g per thousand")
    click.echo(determination.explain())

    broken = check_seed_weight(determination, species)
    if broken:
        for rule in broken:
            click.echo(f"refused: {rule.detail}", err=True)
        raise SystemExit(2)


@seedweight.command("show")
@click.argument("reference")
@click.pass_obj
def show_seed_weight(context, reference: str) -> None:
    """Every thousand seed weight determination on a lot."""
    station = open_station(context.database)
    station.lots.require(reference)
    stored = station.seed_weight.for_lot(reference)

    if not stored:
        click.echo("nothing determined yet")
        return

    for index, determination in enumerate(stored, start=1):
        click.echo(
            f"{index}. {determination.grams_per_thousand} g per thousand   "
            f"{determination.explain()}"
        )
