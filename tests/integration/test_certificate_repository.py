"""Certificates, round tripped through the database."""

from __future__ import annotations

import sqlite3
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
from arc.errors import NotFound
from arc.quantities import Percentage
from arc.storage.certificates import (
    CertificateRepository,
    results_from_json,
    results_to_json,
)
from arc.storage.lots import LotRepository

BOOKED = date(2024, 9, 18)


@pytest.fixture
def certificates(tmp_path):
    connection = open_test_database(tmp_path / "arc.sqlite3")
    LotRepository(connection).save(make_lot(), booked_in_on=BOOKED)
    yield CertificateRepository(connection)
    connection.close()


def full_results() -> Determinations:
    return Determinations(
        pure_seed=Percentage("98.4"),
        other_seed=Percentage("0.8"),
        inert_matter=Percentage("0.8"),
        germination_percent=96,
        germination_tested_on=date(2024, 9, 28),
        moisture_percent=Decimal("14.0"),
        thousand_seed_weight_g=Decimal("45.0"),
        other_species_found=("Avena fatua",),
    )


def a_certificate(
    *,
    serial: int = 187,
    results: Determinations | None = None,
    issued_on: date = date(2024, 10, 2),
    supersedes: CertificateNumber | None = None,
) -> Certificate:
    return Certificate(
        number=CertificateNumber("GB-0214", 2024, serial),
        kind=CertificateKind.ORANGE_INTERNATIONAL,
        lot_reference="L-2024-0041",
        species_name="Triticum aestivum",
        merchant="Ravenscar Grain",
        origin_country="GB",
        lot_weight_kg=Decimal("24000"),
        results=results if results is not None else full_results(),
        issued_on=issued_on,
        signed_by="A. Pearce",
        supersedes=supersedes,
    )


class TestTheResultsColumn:
    def test_a_full_set_survives_the_round_trip(self) -> None:
        original = full_results()

        assert results_from_json(results_to_json(original)) == original

    def test_a_percentage_does_not_become_a_float_on_the_way(self) -> None:
        recovered = results_from_json(results_to_json(full_results()))

        assert recovered.pure_seed == Percentage("98.4")
        assert str(recovered.pure_seed) == "98.4"

    def test_a_moisture_keeps_its_decimal_place(self) -> None:
        recovered = results_from_json(results_to_json(full_results()))

        assert str(recovered.moisture_percent) == "14.0"

    def test_a_determination_nobody_made_stays_absent(self) -> None:
        recovered = results_from_json(results_to_json(Determinations()))

        assert recovered.germination_percent is None
        assert recovered.pure_seed is None
        assert recovered.determinations() == ()

    def test_the_other_species_come_back_as_a_tuple(self) -> None:
        recovered = results_from_json(results_to_json(full_results()))

        assert recovered.other_species_found == ("Avena fatua",)


class TestIssuing:
    def test_a_certificate_comes_back_as_it_went_in(self, certificates) -> None:
        original = a_certificate()

        certificates.issue(original)

        assert certificates.require("GB-0214/2024/00187") == original

    def test_one_nobody_issued_is_not_found(self, certificates) -> None:
        assert certificates.find("GB-0214/2024/00999") is None

        with pytest.raises(NotFound):
            certificates.require("GB-0214/2024/00999")

    def test_the_same_number_cannot_be_issued_twice(self, certificates) -> None:
        certificates.issue(a_certificate())

        with pytest.raises(sqlite3.IntegrityError):
            certificates.issue(a_certificate())

    def test_a_certificate_for_a_lot_that_does_not_exist_is_refused(
        self, certificates
    ) -> None:
        orphan = Certificate(
            number=CertificateNumber("GB-0214", 2024, 900),
            kind=CertificateKind.GREEN_ANALYSIS,
            lot_reference="L-2024-9999",
            species_name="Triticum aestivum",
            merchant="Ravenscar Grain",
            origin_country="GB",
            lot_weight_kg=Decimal("24000"),
            results=Determinations(),
            issued_on=date(2024, 10, 2),
            signed_by="A. Pearce",
        )

        with pytest.raises(sqlite3.IntegrityError):
            certificates.issue(orphan)

    def test_everything_for_one_lot_comes_back_in_number_order(self, certificates) -> None:
        certificates.issue(a_certificate(serial=190))
        certificates.issue(a_certificate(serial=187))

        found = certificates.for_lot("L-2024-0041")

        assert [c.number.serial for c in found] == [187, 190]

    def test_certificates_can_be_pulled_out_by_month(self, certificates) -> None:
        certificates.issue(a_certificate(serial=187, issued_on=date(2024, 9, 30)))
        certificates.issue(a_certificate(serial=188, issued_on=date(2024, 10, 2)))
        certificates.issue(a_certificate(serial=189, issued_on=date(2024, 11, 4)))

        october = certificates.issued_between(date(2024, 10, 1), date(2024, 10, 31))

        assert [c.number.serial for c in october] == [188]


class TestWithdrawing:
    def test_a_withdrawn_certificate_keeps_its_row(self, certificates) -> None:
        certificates.issue(a_certificate())

        certificates.withdraw("GB-0214/2024/00187", on=date(2024, 11, 1))
        found = certificates.require("GB-0214/2024/00187")

        assert found.is_withdrawn
        assert found.withdrawn_on == date(2024, 11, 1)

    def test_withdrawing_one_that_is_already_withdrawn_is_refused(
        self, certificates
    ) -> None:
        certificates.issue(a_certificate())
        certificates.withdraw("GB-0214/2024/00187", on=date(2024, 11, 1))

        with pytest.raises(NotFound):
            certificates.withdraw("GB-0214/2024/00187", on=date(2024, 11, 2))

    def test_withdrawing_one_that_does_not_exist_is_refused(self, certificates) -> None:
        with pytest.raises(NotFound):
            certificates.withdraw("GB-0214/2024/00999", on=date(2024, 11, 1))

    def test_a_replacement_names_what_it_supersedes(self, certificates) -> None:
        certificates.issue(a_certificate(serial=187))
        certificates.withdraw("GB-0214/2024/00187", on=date(2024, 11, 1))
        certificates.issue(
            a_certificate(serial=188, supersedes=CertificateNumber("GB-0214", 2024, 187))
        )

        replacement = certificates.require("GB-0214/2024/00188")

        assert replacement.is_replacement
        assert str(replacement.supersedes) == "GB-0214/2024/00187"


class TestNumbering:
    def test_the_first_certificate_of_a_year_is_number_one(self, certificates) -> None:
        assert certificates.next_serial(2024) == 1

    def test_it_carries_on_from_the_highest_issued(self, certificates) -> None:
        certificates.issue(a_certificate(serial=187))

        assert certificates.next_serial(2024) == 188

    def test_a_gap_is_never_filled_in(self, certificates) -> None:
        certificates.issue(a_certificate(serial=187))
        certificates.issue(a_certificate(serial=200))

        assert certificates.next_serial(2024) == 201

    def test_each_year_counts_on_its_own(self, certificates) -> None:
        certificates.issue(a_certificate(serial=187))

        assert certificates.next_serial(2025) == 1
