"""Two mistakes that are cheap to make and impossible to undo.

A version number used twice, and a migration edited after it has run
somewhere. Both produce a database that is a different shape depending on when
it was built, and neither shows up in a test suite that only ever migrates from
empty.

Run as a program so CI can call it, and importable so a test can too.
"""

from __future__ import annotations

import sys

from arc.storage.schema import MIGRATIONS

__all__ = ["problems", "main"]


def problems() -> list[str]:
    """Everything wrong with the migration list, in the order it was found."""
    found: list[str] = []

    seen: set[int] = set()
    for migration in MIGRATIONS:
        if migration.version in seen:
            found.append(f"version {migration.version} is used more than once")
        seen.add(migration.version)

    versions = [migration.version for migration in MIGRATIONS]
    if versions != sorted(versions):
        found.append("the migrations are not written in version order")

    expected = list(range(1, len(MIGRATIONS) + 1))
    if sorted(versions) != expected:
        found.append(f"expected versions {expected} and found {sorted(versions)}")

    for migration in MIGRATIONS:
        if not migration.name.strip():
            found.append(f"version {migration.version} does not say what it is for")
        if not migration.statements:
            found.append(f"version {migration.version} does nothing")

    return found


def main() -> int:
    found = problems()
    if not found:
        print(f"{len(MIGRATIONS)} migrations, numbered and in order")
        return 0

    for problem in found:
        print(problem, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
