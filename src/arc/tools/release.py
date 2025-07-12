"""Whether the tree is fit to be a release.

Not a substitute for the tests. These are the things that are true of a
release and are not true of a working copy, and every one of them has been
wrong here at least once: a version in two places that disagree, a readme the
metadata points at and nobody wrote, a migration numbered twice.

Run as a program so a release job can call it, importable so a test can.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import arc
from arc.tools.check_migrations import problems as migration_problems

__all__ = ["Problem", "examine", "main"]

#: Where the project file is, relative to this module. Four parents up:
#: release.py, tools, arc, src.
PROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


@dataclass(frozen=True)
class Problem:
    """One reason the tree is not a release."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def examine(project: Path = PROJECT) -> list[Problem]:
    """Everything wrong with the tree, in the order it was found."""
    found: list[Problem] = []

    if not project.exists():
        return [Problem("NO_PROJECT_FILE", f"{project} is not there")]

    config = tomllib.loads(project.read_text(encoding="utf-8"))
    root = project.parent

    found.extend(_version(config))
    found.extend(_readme(config, root))
    found.extend(_pins(config))
    found.extend(Problem("MIGRATIONS", detail) for detail in migration_problems())

    return found


def _version(config: dict[str, Any]) -> list[Problem]:
    declared = config["project"]["version"]

    if declared != arc.__version__:
        return [
            Problem(
                "VERSION_DISAGREES",
                f"pyproject says {declared} and the package says {arc.__version__}",
            )
        ]

    parts = declared.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return [Problem("VERSION_SHAPE", f"{declared} is not three numbers")]

    return []


def _readme(config: dict[str, Any], root: Path) -> list[Problem]:
    named = config["project"].get("readme")
    if named is None:
        return [Problem("NO_README_DECLARED", "the metadata does not name a readme")]

    path = root / named
    if not path.exists():
        return [Problem("README_MISSING", f"the metadata points at {named}")]
    if not path.read_text(encoding="utf-8").strip():
        return [Problem("README_EMPTY", f"{named} has nothing in it")]

    return []


def _pins(config: dict[str, Any]) -> list[Problem]:
    found: list[Problem] = []

    groups = [
        ("dependencies", config["project"].get("dependencies", [])),
        ("build-system", config["build-system"]["requires"]),
    ]
    for name, group in config["project"].get("optional-dependencies", {}).items():
        groups.append((name, group))

    for where, requirements in groups:
        for requirement in requirements:
            if "==" not in requirement:
                found.append(
                    Problem(
                        "UNPINNED",
                        f"{requirement} in {where} is not pinned to a version",
                    )
                )

    return found


def main() -> int:
    found = examine()

    if not found:
        print(f"arc {arc.__version__} looks like a release")
        return 0

    for problem in found:
        print(str(problem), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
