"""Reading and writing certificates.

The determinations go into one JSON column rather than thirty nullable ones.
That is a deliberate trade: the results are read as a whole, written once, and
never queried across, so a column per figure would buy nothing and would need a
migration every time the handbook adds a determination.

What is not in the JSON is anything the station queries on. The lot, the
species, the issue date and the number are real columns, because "every
certificate issued in September" and "everything for this lot" are questions
somebody asks weekly.

Nothing here updates a certificate. The only writes are issuing one and marking
one withdrawn, because a certificate that has left the building cannot be
changed, only replaced.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal

from arc.certificates.model import (
    Certificate,
    CertificateKind,
    CertificateNumber,
    Determinations,
    OtherSeedCount,
    OtherSeedReport,
)
from arc.errors import NotFound
from arc.quantities import Percentage
from arc.storage.codec import to_date, to_decimal, to_iso, to_optional_date, to_text

__all__ = ["CertificateRepository", "results_to_json", "results_from_json"]


def results_to_json(results: Determinations) -> str:
    """The determinations as text, with every number kept exact.

    Decimals go in as strings. JSON has one number type and it is a float, and
    a purity of 98.4 that comes back as 98.39999999999999 is a certificate that
    no longer sums to a hundred.
    """
    payload: dict[str, object] = {
        "pure_seed": None if results.pure_seed is None else str(results.pure_seed),
        "other_seed": None if results.other_seed is None else str(results.other_seed),
        "inert_matter": None if results.inert_matter is None else str(results.inert_matter),
        "germination_percent": results.germination_percent,
        "germination_tested_on": None
        if results.germination_tested_on is None
        else to_iso(results.germination_tested_on),
        "hard_seed_percent": results.hard_seed_percent,
        "moisture_percent": None
        if results.moisture_percent is None
        else to_text(results.moisture_percent),
        "thousand_seed_weight_g": None
        if results.thousand_seed_weight_g is None
        else to_text(results.thousand_seed_weight_g),
        "other_seed_report": None
        if results.other_seed_report is None
        else {
            "kind": results.other_seed_report.kind,
            "weight_examined_g": to_text(results.other_seed_report.weight_examined_g),
            "sought": list(results.other_seed_report.sought),
            "counts": [
                {
                    "species_name": found.species_name,
                    "count": found.count,
                    "per_kg": to_text(found.per_kg),
                }
                for found in results.other_seed_report.counts
            ],
        },
    }
    return json.dumps(payload, sort_keys=True)


def results_from_json(text: str) -> Determinations:
    payload = json.loads(text)

    def percentage(key: str) -> Percentage | None:
        raw = payload.get(key)
        return None if raw is None else Percentage(raw)

    def decimal(key: str) -> Decimal | None:
        raw = payload.get(key)
        return None if raw is None else to_decimal(raw)

    tested_on = payload.get("germination_tested_on")

    def other_seed_report() -> OtherSeedReport | None:
        raw = payload.get("other_seed_report")
        if raw is None:
            return None
        return OtherSeedReport(
            kind=raw["kind"],
            weight_examined_g=to_decimal(raw["weight_examined_g"]),
            counts=tuple(
                OtherSeedCount(
                    species_name=found["species_name"],
                    count=int(found["count"]),
                    per_kg=to_decimal(found["per_kg"]),
                )
                for found in raw.get("counts", ())
            ),
            sought=tuple(raw.get("sought", ())),
        )

    return Determinations(
        pure_seed=percentage("pure_seed"),
        other_seed=percentage("other_seed"),
        inert_matter=percentage("inert_matter"),
        germination_percent=payload.get("germination_percent"),
        germination_tested_on=None if tested_on is None else to_date(tested_on),
        hard_seed_percent=payload.get("hard_seed_percent"),
        moisture_percent=decimal("moisture_percent"),
        thousand_seed_weight_g=decimal("thousand_seed_weight_g"),
        other_seed_report=other_seed_report(),
    )


class CertificateRepository:
    """Certificates, issued and withdrawn but never edited."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def issue(self, certificate: Certificate) -> Certificate:
        self._connection.execute(
            """
            insert into certificate
                (number, kind, lot_reference, species_name, merchant, origin_country,
                 lot_weight_kg, issued_on, signed_by, supersedes, withdrawn_on,
                 results_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(certificate.number),
                certificate.kind.value,
                certificate.lot_reference,
                certificate.species_name,
                certificate.merchant,
                certificate.origin_country,
                to_text(certificate.lot_weight_kg),
                to_iso(certificate.issued_on),
                certificate.signed_by,
                str(certificate.supersedes) if certificate.supersedes else None,
                to_iso(certificate.withdrawn_on) if certificate.withdrawn_on else None,
                results_to_json(certificate.results),
            ),
        )
        return certificate

    def withdraw(self, number: CertificateNumber | str, *, on: date) -> None:
        """Marks one withdrawn. The row stays; somebody holds a copy of it."""
        cursor = self._connection.execute(
            "update certificate set withdrawn_on = ? where number = ? and withdrawn_on is null",
            (to_iso(on), str(number)),
        )
        if cursor.rowcount == 0:
            raise NotFound("open certificate", str(number))

    def find(self, number: CertificateNumber | str) -> Certificate | None:
        row = self._connection.execute(
            "select * from certificate where number = ?", (str(number),)
        ).fetchone()
        return None if row is None else self._to_certificate(row)

    def require(self, number: CertificateNumber | str) -> Certificate:
        found = self.find(number)
        if found is None:
            raise NotFound("certificate", str(number))
        return found

    def for_lot(self, lot_reference: str) -> tuple[Certificate, ...]:
        rows = self._connection.execute(
            "select * from certificate where lot_reference = ? order by number asc",
            (lot_reference,),
        ).fetchall()
        return tuple(self._to_certificate(row) for row in rows)

    def issued_between(self, start: date, end: date) -> tuple[Certificate, ...]:
        rows = self._connection.execute(
            """
            select * from certificate
            where issued_on between ? and ?
            order by issued_on asc, number asc
            """,
            (to_iso(start), to_iso(end)),
        ).fetchall()
        return tuple(self._to_certificate(row) for row in rows)

    def next_serial(self, year: int) -> int:
        """The next serial for the year, which is one past the highest used.

        Gaps are fine and are never reused. A certificate number that was
        allocated and then not issued is a number nobody will ever see, and
        reusing it would mean two certificates with the same number a year
        apart.
        """
        row = self._connection.execute(
            """
            select max(cast(substr(number, length(number) - 4) as integer)) as highest
            from certificate
            where substr(number, 9, 4) = ?
            """,
            (str(year),),
        ).fetchone()
        highest = row["highest"] if row and row["highest"] is not None else 0
        return int(highest) + 1

    @staticmethod
    def _to_certificate(row: sqlite3.Row) -> Certificate:
        supersedes = row["supersedes"]
        return Certificate(
            number=CertificateNumber.parse(row["number"]),
            kind=CertificateKind(row["kind"]),
            lot_reference=row["lot_reference"],
            species_name=row["species_name"],
            merchant=row["merchant"],
            origin_country=row["origin_country"],
            lot_weight_kg=to_decimal(row["lot_weight_kg"]),
            results=results_from_json(row["results_json"]),
            issued_on=to_date(row["issued_on"]),
            signed_by=row["signed_by"],
            supersedes=CertificateNumber.parse(supersedes) if supersedes else None,
            withdrawn_on=to_optional_date(row["withdrawn_on"]),
        )
