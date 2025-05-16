"""What the package says about itself.

Small, and worth having. Every one of these has been wrong in some project at
some point, and none of them fails in a way anybody notices until the wheel is
on a machine that is not this one.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

import arc

PROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return tomllib.loads(PROJECT.read_text(encoding="utf-8"))


class TestTheStationItSaysItIs:
    def test_the_code_is_the_one_on_the_certificates(self) -> None:
        assert arc.STATION_CODE == "GB-0214"

    def test_the_name_is_the_one_on_the_certificates(self) -> None:
        assert arc.STATION_NAME == "Ravenscar Seed Testing Station"

    def test_there_is_a_version(self) -> None:
        assert arc.__version__.count(".") == 2


class TestTheVersionMatches:
    def test_the_package_and_the_project_agree(self, config: dict[str, Any]) -> None:
        assert config["project"]["version"] == arc.__version__


class TestPinning:
    def test_every_dependency_is_pinned_exactly(self, config) -> None:
        # A station with no operations team does not want a release to move
        # under it because a transitive dependency published on a Tuesday.
        for requirement in config["project"]["dependencies"]:
            assert "==" in requirement, requirement

    def test_and_so_is_every_development_dependency(self, config) -> None:
        for requirement in config["project"]["optional-dependencies"]["dev"]:
            assert "==" in requirement, requirement

    def test_the_build_backend_is_pinned_too(self, config) -> None:
        for requirement in config["build-system"]["requires"]:
            assert "==" in requirement, requirement


class TestTheToolsAgreeWithEachOther:
    def test_ruff_targets_the_python_the_project_requires(self, config) -> None:
        requires = config["project"]["requires-python"]
        target = config["tool"]["ruff"]["target-version"]

        assert requires == ">=3.12"
        assert target == "py312"

    def test_mypy_checks_against_the_same_one(self, config) -> None:
        assert config["tool"]["mypy"]["python_version"] == "3.12"

    def test_the_tests_live_where_pytest_looks(self, config) -> None:
        assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]

    def test_and_pytest_can_find_the_package(self, config) -> None:
        assert config["tool"]["pytest"]["ini_options"]["pythonpath"] == ["src"]

    def test_mypy_checks_the_tests_as_well_as_the_source(self, config) -> None:
        assert config["tool"]["mypy"]["files"] == ["src", "tests"]

    def test_but_not_strictly(self, config) -> None:
        overrides = config["tool"]["mypy"]["overrides"]
        for_tests = [item for item in overrides if item["module"] == "tests.*"]

        assert for_tests
        assert for_tests[0]["disallow_untyped_defs"] is False


class TestTheReadme:
    def test_the_file_the_metadata_names_is_there(self, config: dict[str, Any]) -> None:
        # Without this the package cannot be built at all: hatchling reads the
        # readme to put it in the metadata and fails when it is missing, which
        # takes out every install and every wheel.
        named = config["project"]["readme"]

        assert (PROJECT.parent / named).exists()

    def test_and_has_something_in_it(self, config: dict[str, Any]) -> None:
        named = config["project"]["readme"]
        text = (PROJECT.parent / named).read_text(encoding="utf-8")

        assert len(text.splitlines()) > 20

    def test_it_names_the_command(self, config: dict[str, Any]) -> None:
        text = (PROJECT.parent / config["project"]["readme"]).read_text(encoding="utf-8")

        assert "arc lot book-in" in text


class TestTheTypeMarker:
    def test_it_is_there(self) -> None:
        assert (Path(arc.__file__).parent / "py.typed").exists()

    def test_and_the_wheel_is_told_to_carry_it(self, config) -> None:
        wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]

        assert "src/arc/py.typed" in wheel["artifacts"]


class TestTheEntryPoint:
    def test_the_command_is_called_arc(self, config) -> None:
        assert "arc" in config["project"]["scripts"]

    def test_and_points_at_something_that_exists(self, config) -> None:
        target = config["project"]["scripts"]["arc"]
        module_name, function_name = target.split(":")

        module = __import__(module_name, fromlist=[function_name])

        assert callable(getattr(module, function_name))
