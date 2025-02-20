"""The Monday morning check.

Each of these builds a database that is wrong in exactly one way and then asks
the doctor about it. The one that matters most is the opposite: a station that
did everything right has to come back clean, or the report becomes noise
somebody stops reading.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.conftest import make_lot
from tests.support import open_test_database

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
)
from arc.germination.model import Treatment
from arc.lots.model import LotStatus
from arc.quantities import Percentage
from arc.referee.between_labs import compare_germination
from arc.retention.model import Determination, DisposalReason, RetainedSample
from arc.storage.certificates import CertificateRepository
from arc.storage.lots import LotRepository
from arc.storage.referee import RefereeRepository
from arc.storage.retention import RetentionRepository
from arc.tools.doctor import Severity, examine, held_samples

BOOKED = date(2025, 1, 6)
TODAY = date(2025, 1, 13)
LOT = "L-2024-0041"
NUMBER = "GB-0214/2024/00187"


@pytest.fixture
def db(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    yield connection
    connection.close()


def book(db, *, serial: int = 41, status: LotStatus | None = None, on: date = BOOKED):
    lot = make_lot(serial=serial)
    if status is not None:
        lot.move_to(LotStatus.SAMPLED)
        if status is LotStatus.IN_TEST:
            lot.move_to(LotStatus.IN_TEST)
    LotRepository(db).save(lot, booked_in_on=on)
    return lot


def certify(db, *, serial: int = 187, lot_reference: str = LOT) -> None:
    CertificateRepository(db).issue(
        Certificate(
            number=CertificateNumber("GB-0214", 2024, serial),
            kind=CertificateKind.ORANGE_INTERNATIONAL,
            lot_reference=lot_reference,
            species_name="Triticum aestivum",
            merchant="Ravenscar Grain",
            origin_country="GB",
            lot_weight_kg=Decimal("24000"),
            results=Determinations(
                pure_seed=Percentage("98.4"),
                other_seed=Percentage("0.8"),
                inert_matter=Percentage("0.8"),
                germination_percent=96,
                germination_tested_on=date(2024, 12, 20),
                germination_treatment=Treatment.NONE,
            ),
            issued_on=date(2024, 12, 30),
            signed_by="A. Pearce",
        )
    )


def place(db, *, lot_reference: str = LOT, remaining: str = "860.0") -> None:
    RetentionRepository(db).place(
        RetainedSample(
            lot_reference=lot_reference,
            species_name="Triticum aestivum",
            remaining_g=Decimal(remaining),
            held_from=date(2024, 12, 30),
            certificate_kind=CertificateKind.ORANGE_INTERNATIONAL,
        )
    )


def codes(db, on: date = TODAY) -> list[str]:
    return [finding.code for finding in examine(db, on=on)]


class TestAStationThatDidEverythingRight:
    def test_an_empty_database_is_clean(self, db) -> None:
        assert examine(db, on=TODAY) == []

    def test_a_certified_lot_with_its_jar_is_clean(self, db) -> None:
        book(db)
        certify(db)
        place(db)

        assert examine(db, on=TODAY) == []

    def test_and_the_store_count_is_right(self, db) -> None:
        book(db)
        certify(db)
        place(db)

        assert held_samples(db) == 1


class TestTheSchema:
    def test_a_database_missing_a_migration(self, db) -> None:
        db.execute("delete from schema_migration where version = 8")

        assert "SCHEMA_BEHIND" in codes(db)

    def test_a_database_written_by_a_newer_release(self, db) -> None:
        db.execute(
            "insert into schema_migration (version, name) values (99, 'from the future')"
        )

        assert "SCHEMA_AHEAD" in codes(db)

    def test_and_that_one_is_serious(self, db) -> None:
        db.execute(
            "insert into schema_migration (version, name) values (99, 'from the future')"
        )

        findings = examine(db, on=TODAY)

        assert findings[0].severity is Severity.SERIOUS


class TestACertificateWithNothingBehindIt:
    def test_a_certificate_whose_sample_was_never_placed(self, db) -> None:
        book(db)
        certify(db)

        assert "CERTIFICATE_WITHOUT_A_SAMPLE" in codes(db)

    def test_and_the_message_says_which(self, db) -> None:
        book(db)
        certify(db)

        detail = [f.detail for f in examine(db, on=TODAY)][0]

        assert "never placed" in detail
        assert NUMBER in detail

    def test_a_certificate_whose_sample_was_thrown_out(self, db) -> None:
        book(db)
        certify(db)
        place(db)
        RetentionRepository(db).dispose(LOT, on=date(2025, 1, 2), reason=DisposalReason.SPOILED)

        findings = [f for f in examine(db, on=TODAY) if f.code.startswith("CERT")]

        assert findings
        assert "was disposed of" in findings[0].detail

    def test_a_withdrawn_certificate_does_not_need_one(self, db) -> None:
        book(db)
        certify(db)
        CertificateRepository(db).withdraw(NUMBER, on=date(2025, 1, 5))

        assert "CERTIFICATE_WITHOUT_A_SAMPLE" not in codes(db)


class TestTheStore:
    def test_a_jar_recorded_as_holding_less_than_nothing(self, db) -> None:
        book(db)
        place(db)
        db.execute(
            "update retained_sample set remaining_g = '-40.0' where lot_reference = ?",
            (LOT,),
        )

        assert "STORE_WEIGHT_NEGATIVE" in codes(db)

    def test_a_jar_that_has_been_drawn_on_normally_is_fine(self, db) -> None:
        book(db)
        place(db)
        RetentionRepository(db).draw(
            LOT,
            Determination.PURITY,
            Decimal("120.0"),
            on=date(2025, 1, 8),
            analyst="R. Naylor",
        )

        assert "STORE_WEIGHT_NEGATIVE" not in codes(db)


class TestWorkThatStopped:
    def test_a_lot_sitting_in_test_for_two_months(self, db) -> None:
        book(db, status=LotStatus.IN_TEST, on=date(2024, 10, 1))

        assert "LOT_STUCK_IN_TEST" in codes(db)

    def test_one_booked_in_last_week_is_not_stuck(self, db) -> None:
        book(db, status=LotStatus.IN_TEST, on=date(2025, 1, 8))

        assert "LOT_STUCK_IN_TEST" not in codes(db)

    def test_and_it_is_only_worth_a_look(self, db) -> None:
        book(db, status=LotStatus.IN_TEST, on=date(2024, 10, 1))

        findings = examine(db, on=TODAY)

        assert findings[0].severity is Severity.WORTH_A_LOOK


class TestDisputesNobodyAnswered:
    def test_one_from_last_month(self, db) -> None:
        book(db)
        RefereeRepository(db).record(
            LOT,
            NUMBER,
            Determination.GERMINATION,
            compare_germination(96, 80),
            other_laboratory="NL-0510 Wageningen",
            raised_by="Ravenscar Grain",
            on=date(2024, 11, 20),
        )

        assert "DISPUTE_UNANSWERED" in codes(db)

    def test_one_from_this_week_is_not_stale_yet(self, db) -> None:
        book(db)
        RefereeRepository(db).record(
            LOT,
            NUMBER,
            Determination.GERMINATION,
            compare_germination(96, 80),
            other_laboratory="NL-0510 Wageningen",
            raised_by="Ravenscar Grain",
            on=date(2025, 1, 9),
        )

        assert "DISPUTE_UNANSWERED" not in codes(db)

    def test_a_comparison_that_agreed_is_never_stale(self, db) -> None:
        book(db)
        RefereeRepository(db).record(
            LOT,
            NUMBER,
            Determination.GERMINATION,
            compare_germination(96, 94),
            other_laboratory="NL-0510 Wageningen",
            raised_by="Ravenscar Grain",
            on=date(2024, 11, 20),
        )

        assert "DISPUTE_UNANSWERED" not in codes(db)


class TestTheOrderTheyComeIn:
    def test_the_serious_ones_come_first(self, db) -> None:
        book(db, status=LotStatus.IN_TEST, on=date(2024, 10, 1))
        certify(db)

        findings = examine(db, on=TODAY)

        assert [finding.severity for finding in findings] == [
            Severity.SERIOUS,
            Severity.WORTH_A_LOOK,
        ]

    def test_a_finding_prints_its_severity_and_its_code(self, db) -> None:
        book(db)
        certify(db)

        assert str(examine(db, on=TODAY)[0]).startswith(
            "[serious] CERTIFICATE_WITHOUT_A_SAMPLE:"
        )
