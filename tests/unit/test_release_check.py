"""The check that says whether the tree could be shipped.

Every one of these has actually been wrong in this repository at some point,
which is the reason the check exists rather than a hypothetical. The readme one
in particular: the metadata pointed at a file nobody had written, so the package
could not be built at all, and nothing noticed for months.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import arc
from arc.tools import release


def a_project(
    tmp_path: Path,
    *,
    version: str | None = None,
    readme: str | None = "README.md",
    write_readme: bool = True,
    dependency: str = "click==8.1.8",
    dev: str = "pytest==8.3.4",
    build: str = "hatchling==1.27.0",
) -> Path:
    """A pyproject that is fine unless one thing is changed."""
    readme_line = f'readme = "{readme}"\n' if readme is not None else ""
    text = f"""
[build-system]
requires = ["{build}"]
build-backend = "hatchling.build"

[project]
name = "arc"
version = "{version or arc.__version__}"
{readme_line}dependencies = ["{dependency}"]

[project.optional-dependencies]
dev = ["{dev}"]
"""
    path = tmp_path / "pyproject.toml"
    path.write_text(text, encoding="utf-8")

    if readme is not None and write_readme:
        (tmp_path / readme).write_text("# arc\n\nSomething about it.\n", encoding="utf-8")

    return path


def codes(path: Path) -> list[str]:
    return [problem.code for problem in release.examine(path)]


class TestTheRealTree:
    def test_it_is_fit_to_ship(self) -> None:
        assert release.examine() == []

    def test_the_program_says_so_and_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert release.main() == 0
        assert arc.__version__ in capsys.readouterr().out

    def test_the_version_is_a_release_version(self) -> None:
        assert arc.__version__ == "1.0.0"


class TestTheVersion:
    def test_a_project_that_agrees_with_the_package(self, tmp_path) -> None:
        assert codes(a_project(tmp_path)) == []

    def test_one_that_does_not(self, tmp_path) -> None:
        problems = release.examine(a_project(tmp_path, version="0.9.0"))

        assert [p.code for p in problems] == ["VERSION_DISAGREES"]
        assert arc.__version__ in problems[0].detail

    def test_a_version_that_is_not_three_numbers(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(arc, "__version__", "1.0")

        assert codes(a_project(tmp_path, version="1.0")) == ["VERSION_SHAPE"]

    def test_a_version_with_a_suffix_on_it(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(arc, "__version__", "1.0.0rc1")

        assert codes(a_project(tmp_path, version="1.0.0rc1")) == ["VERSION_SHAPE"]


class TestTheReadme:
    def test_one_that_is_there(self, tmp_path) -> None:
        assert codes(a_project(tmp_path)) == []

    def test_metadata_pointing_at_a_file_nobody_wrote(self, tmp_path) -> None:
        assert codes(a_project(tmp_path, write_readme=False)) == ["README_MISSING"]

    def test_a_readme_with_nothing_in_it(self, tmp_path) -> None:
        path = a_project(tmp_path)
        (tmp_path / "README.md").write_text("   \n", encoding="utf-8")

        assert codes(path) == ["README_EMPTY"]

    def test_metadata_that_names_no_readme_at_all(self, tmp_path) -> None:
        assert codes(a_project(tmp_path, readme=None)) == ["NO_README_DECLARED"]


class TestThePins:
    def test_everything_pinned(self, tmp_path) -> None:
        assert codes(a_project(tmp_path)) == []

    def test_a_dependency_left_loose(self, tmp_path) -> None:
        problems = release.examine(a_project(tmp_path, dependency="click>=8"))

        assert [p.code for p in problems] == ["UNPINNED"]
        assert "dependencies" in problems[0].detail

    def test_a_development_dependency_left_loose(self, tmp_path) -> None:
        assert codes(a_project(tmp_path, dev="pytest")) == ["UNPINNED"]

    def test_the_build_backend_left_loose(self, tmp_path) -> None:
        problems = release.examine(a_project(tmp_path, build="hatchling"))

        assert "build-system" in problems[0].detail


class TestWhenThereIsNoProjectAtAll:
    def test_it_says_so_rather_than_raising(self, tmp_path) -> None:
        assert codes(tmp_path / "nothing.toml") == ["NO_PROJECT_FILE"]


class TestTheProgram:
    def test_a_broken_tree_exits_non_zero(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(
            release, "examine", lambda: [release.Problem("BROKEN", "on purpose")]
        )

        assert release.main() == 1
        assert "BROKEN: on purpose" in capsys.readouterr().err

    def test_a_problem_prints_its_code_and_its_reason(self) -> None:
        assert str(release.Problem("CODE", "why")) == "CODE: why"
