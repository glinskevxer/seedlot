"""Moisture and thousand seed weight, from the bench to the certificate.

Both of these are optional determinations, and both of them have a way of
being wrong that looks like being absent. A moisture that was determined in two
stages must reach the certificate as the combination of the two rather than as
the second stage on its own, and a seed weight whose replicates scattered too
far must stop the certificate rather than quietly not appear on it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import CertificateKind
from arc.errors import RuleBroken
from arc.germination.model import GerminationTest, Replicate
from arc.lots.model import LotStatus
from arc.moisture.determination import Weighing, moisture_of
from arc.purity.analysis import PurityAnalysis, analyse
from arc.species import register
from arc.storage.certificates import CertificateRepository
from arc.storage.determinations import GerminationRepository, PurityRepository
from arc.storage.lots import LotRepository
from arc.storage.physical import MoistureRepository, SeedWeightRepository
from arc.weight.thousand_seed import measure
from arc.workflow.issuing import gather, issue

BOOKED = date(2024, 7, 18)
DETERMINED = date(2024, 7, 25)
ISSUED = date(2024, 7, 30)
LOT = "L-2024-0041"

TIDY = tuple(
    Decimal(value) for value in ("4.51", "4.48", "4.52", "4.49", "4.50", "4.53", "4.47", "4.50")
)
SCATTERED = tuple(
    Decimal(value) for value in ("4.90", "4.10", "4.80", "4.20", "4.75", "4.25", "4.60", "4.40")
)


class Bench:
    def __init__(self, path) -> None:
        self.connection = open_test_database(path)
        self.lots = LotRepository(self.connection)
        self.purity = PurityRepository(self.connection)
        self.germination = GerminationRepository(self.connection)
        self.moisture = MoistureRepository(self.connection)
        self.seed_weight = SeedWeightRepository(self.connection)
        self.certificates = CertificateRepository(self.connection)


@pytest.fixture
def bench(tmp_path):
    built = Bench(tmp_path / "arc.sqlite3")
    lot = make_lot()
    lot.move_to(LotStatus.SAMPLED)
    lot.move_to(LotStatus.IN_TEST)
    built.lots.save(lot, booked_in_on=BOOKED)
    yield built
    built.connection.close()


def weighing(container="12.000", wet="22.000", dry="20.600") -> Weighing:
    return Weighing(
        container_g=Decimal(container),
        with_sample_g=Decimal(wet),
        after_drying_g=Decimal(dry),
    )


def record_the_usual(bench) -> None:
    analysis = PurityAnalysis(
        working_sample_g=Decimal("120.0"),
        pure_seed_g=Decimal("118.2"),
        other_seed_g=Decimal("0.9"),
        inert_matter_g=Decimal("0.9"),
        analyst="J. Whitfield",
    )
    bench.purity.record(
        LOT,
        analysis,
        analyse(analysis, register.require("wheat")),
        analysed_on=DETERMINED,
        is_duplicate=False,
    )
    bench.germination.record(
        GerminationTest(
            lot_reference=LOT,
            species_name="Triticum aestivum",
            replicates=tuple(
                Replicate(normal=n, abnormal=100 - n, hard=0, fresh=0, dead=0)
                for n in (96, 95, 97, 96)
            ),
            seeds_per_replicate=100,
            set_down_on=date(2024, 7, 20),
            final_count_on=date(2024, 7, 28),
            analyst="J. Whitfield",
        )
    )


def gathered_for(bench):
    return gather(
        LOT,
        "Triticum aestivum",
        purity=bench.purity,
        germination=bench.germination,
        moisture=bench.moisture,
        seed_weight=bench.seed_weight,
    )


class TestMoistureReachingTheCertificate:
    def test_a_moisture_that_was_never_done_is_absent(self, bench) -> None:
        record_the_usual(bench)

        assert gathered_for(bench).results.moisture_percent is None

    def test_one_that_was_done_comes_through(self, bench) -> None:
        record_the_usual(bench)
        bench.moisture.record(
            LOT,
            weighing(),
            moisture_of(weighing()),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        assert gathered_for(bench).results.moisture_percent == Decimal("14.0")

    def test_and_lands_on_the_issued_certificate(self, bench) -> None:
        record_the_usual(bench)
        bench.moisture.record(
            LOT,
            weighing(),
            moisture_of(weighing()),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        certificate = issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
            moisture=bench.moisture,
            seed_weight=bench.seed_weight,
        )

        assert certificate.results.moisture_percent == Decimal("14.0")
        assert "moisture" in certificate.results.determinations()


class TestSeedWeightReachingTheCertificate:
    def test_a_tidy_set_of_replicates_comes_through(self, bench) -> None:
        record_the_usual(bench)
        bench.seed_weight.record(
            LOT,
            measure(TIDY, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        gathered = gathered_for(bench)

        assert gathered.is_ready
        assert gathered.results.thousand_seed_weight_g == Decimal("45.0")

    def test_a_scattered_set_stops_the_certificate(self, bench) -> None:
        # Wheat is free flowing, so eight replicates spread this far apart
        # mean the counting or the dividing went wrong, and the figure cannot
        # be reported either way.
        record_the_usual(bench)
        bench.seed_weight.record(
            LOT,
            measure(SCATTERED, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        gathered = gathered_for(bench)

        assert gathered.is_ready is False
        assert "SEED_WEIGHT_SCATTER_TOO_WIDE" in [rule.code for rule in gathered.problems]

    def test_and_issuing_is_refused_rather_than_the_figure_being_dropped(self, bench) -> None:
        record_the_usual(bench)
        bench.seed_weight.record(
            LOT,
            measure(SCATTERED, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        with pytest.raises(RuleBroken) as refused:
            issue(
                LOT,
                CertificateKind.ORANGE_INTERNATIONAL,
                signed_by="A. Pearce",
                on=ISSUED,
                lots=bench.lots,
                purity=bench.purity,
                germination=bench.germination,
                certificates=bench.certificates,
                moisture=bench.moisture,
                seed_weight=bench.seed_weight,
            )

        assert "SEED_WEIGHT_SCATTER_TOO_WIDE" in refused.value.codes

    def test_the_latest_determination_is_the_one_reported(self, bench) -> None:
        record_the_usual(bench)
        bench.seed_weight.record(
            LOT,
            measure(SCATTERED, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )
        bench.seed_weight.record(
            LOT,
            measure(TIDY, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=date(2024, 7, 26),
        )

        gathered = gathered_for(bench)

        assert gathered.is_ready
        assert gathered.results.thousand_seed_weight_g == Decimal("45.0")


class TestBothTogether:
    def test_a_certificate_can_carry_all_four_determinations(self, bench) -> None:
        record_the_usual(bench)
        bench.moisture.record(
            LOT,
            weighing(),
            moisture_of(weighing()),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )
        bench.seed_weight.record(
            LOT,
            measure(TIDY, register.require("wheat")),
            analyst="J. Whitfield",
            determined_on=DETERMINED,
        )

        certificate = issue(
            LOT,
            CertificateKind.ORANGE_INTERNATIONAL,
            signed_by="A. Pearce",
            on=ISSUED,
            lots=bench.lots,
            purity=bench.purity,
            germination=bench.germination,
            certificates=bench.certificates,
            moisture=bench.moisture,
            seed_weight=bench.seed_weight,
        )

        assert certificate.results.determinations() == (
            "purity",
            "germination",
            "moisture",
            "thousand seed weight",
        )

    def test_leaving_the_repositories_out_leaves_both_off(self, bench) -> None:
        record_the_usual(bench)

        gathered = gather(
            LOT,
            "Triticum aestivum",
            purity=bench.purity,
            germination=bench.germination,
        )

        assert gathered.results.moisture_percent is None
        assert gathered.results.thousand_seed_weight_g is None
