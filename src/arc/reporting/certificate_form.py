"""The certificate as it is printed.

The station prints onto pre printed stationery on a dot matrix printer, which
sounds like a joke and is not: the orange certificate is a controlled form, the
boxes are in fixed places, and the printer is the only one in the building that
can put ink exactly where the box is. So this renders to a fixed width block of
text and the widths are not decoration.

Nothing here recomputes anything. Every figure comes off the stored certificate
as it was issued, because a form that worked a germination out again could
print something the certificate does not say.
"""

from __future__ import annotations

from arc.certificates.model import Certificate, Determinations

__all__ = ["WIDTH", "render", "render_many"]

#: The form is 78 columns. Wider than that and the last character lands on the
#: perforation.
WIDTH = 78

_LABEL = 24
_RULE = "-" * WIDTH


def render(certificate: Certificate, *, station_name: str, station_code: str) -> str:
    """One certificate, as a block of text for the form."""
    lines: list[str] = []

    lines.append(_centre(station_name.upper()))
    lines.append(_centre(f"STATION {station_code}"))
    lines.append(_centre(certificate.kind.value.upper()))
    lines.append(_RULE)

    lines.append(_field("Certificate number", str(certificate.number)))
    lines.append(_field("Issued", certificate.issued_on.isoformat()))
    lines.append(_field("Signed", certificate.signed_by))

    if certificate.is_replacement:
        lines.append(_field("Supersedes", str(certificate.supersedes)))
    if certificate.is_withdrawn:
        lines.append(_field("WITHDRAWN", str(certificate.withdrawn_on)))

    lines.append(_RULE)
    lines.append(_field("Lot", certificate.lot_reference))
    lines.append(_field("Species", certificate.species_name))
    lines.append(_field("Merchant", certificate.merchant))
    lines.append(_field("Country of origin", certificate.origin_country))
    lines.append(_field("Weight of lot", f"{certificate.lot_weight_kg} kg"))

    lines.append(_RULE)
    lines.extend(_determinations(certificate.results))

    lines.append(_RULE)
    lines.append(_centre("This certificate reports only what was determined."))

    return "\n".join(lines) + "\n"


def render_many(
    certificates: tuple[Certificate, ...],
    *,
    station_name: str,
    station_code: str,
) -> str:
    """A run of certificates, separated by a form feed for the printer."""
    return "\f".join(
        render(certificate, station_name=station_name, station_code=station_code)
        for certificate in certificates
    )


def _determinations(results: Determinations) -> list[str]:
    """The figures, with anything that was not determined left off entirely."""
    lines: list[str] = []

    if results.has_purity:
        lines.append(_field("Pure seed", f"{results.pure_seed} per cent by weight"))
        lines.append(_field("Other seed", f"{results.other_seed} per cent by weight"))
        lines.append(_field("Inert matter", f"{results.inert_matter} per cent by weight"))

    germination = results.germination_line
    if germination is not None:
        lines.append(_field("Germination", germination))
    if results.germination_tested_on is not None:
        lines.append(_field("Tested", results.germination_tested_on.isoformat()))
    if results.hard_seed_percent is not None:
        lines.append(_field("Hard seed", f"{results.hard_seed_percent} per cent"))

    if results.moisture_percent is not None:
        lines.append(_field("Moisture", f"{results.moisture_percent} per cent"))
    if results.thousand_seed_weight_g is not None:
        lines.append(_field("Thousand seed weight", f"{results.thousand_seed_weight_g} g"))

    report = results.other_seed_report
    if report is not None:
        lines.append(_field("Other seed by number", report.line()))
        if report.sought:
            lines.append(_field("Searched for", ", ".join(report.sought)))

    if not lines:
        lines.append(_field("Determinations", "none"))

    return lines


def _field(label: str, value: str) -> str:
    """One labelled box, wrapped onto the next line rather than truncated.

    Truncating would be tidier and is not an option. A merchant name that runs
    off the end of the box is a merchant name that no longer identifies who
    the seed belongs to.
    """
    room = WIDTH - _LABEL
    first, *rest = _wrap(value, room)
    lines = [f"{label:<{_LABEL}}{first}"]
    lines.extend(f"{'':<{_LABEL}}{piece}" for piece in rest)
    return "\n".join(lines)


def _wrap(value: str, room: int) -> list[str]:
    if len(value) <= room:
        return [value]

    pieces: list[str] = []
    line = ""
    for word in value.split(" "):
        if line and len(line) + 1 + len(word) > room:
            pieces.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        pieces.append(line)
    return pieces or [""]


def _centre(text: str) -> str:
    return text.center(WIDTH).rstrip()
