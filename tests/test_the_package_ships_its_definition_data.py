"""The wheel must carry the data the code reads at run time.

v0.12.0 and v0.12.1 shipped `definition/` as code only: the v1 JSON Schemas and
the built-in Profiles and checker Tools stayed in the repository and never
reached the wheel, so an installed copy raised `FileNotFoundError` on the first
`load_definition` — while every test in this repository passed, because they
run against the source tree. Found by a consumer installing the tag.

These tests read through `importlib.resources`, which sees what is installed
rather than what is next to the source file, so they fail on a wheel that has
been stripped of its data even when the source tree is complete.
"""

from __future__ import annotations

from importlib import resources

import pytest

SCHEMAS = (
    "process.v1.schema.json",
    "tool.v1.schema.json",
    "profile.v1.schema.json",
    "control.v1.schema.json",
)
BUILTINS = (
    "control-result.profile.yaml",
    "decision.profile.yaml",
    "profile-conformance.tool.yaml",
    "decision-evidence.tool.yaml",
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_every_v1_schema_is_installed(name: str) -> None:
    schema = resources.files("sulis_workflows.definition") / "schema" / name
    assert schema.is_file(), f"{name} is missing from the installed package"
    assert schema.read_text(encoding="utf-8").strip().startswith("{")


@pytest.mark.parametrize("name", BUILTINS)
def test_every_builtin_definition_is_installed(name: str) -> None:
    document = resources.files("sulis_workflows.definition") / "builtin" / name
    assert document.is_file(), f"{name} is missing from the installed package"
    assert "api_version: sulis.workflows/v1" in document.read_text(encoding="utf-8")


def test_a_definition_loads_against_the_installed_schemas() -> None:
    """The end a consumer actually hits: load something, and have it validate."""
    from sulis_workflows.definition.load import load_definition_file

    builtin = resources.files("sulis_workflows.definition") / "builtin"
    with resources.as_file(builtin / "decision.profile.yaml") as path:
        loaded = load_definition_file(path)

    assert loaded.header.id == "decision"


def test_the_package_declares_itself_typed() -> None:
    """PEP 561: without `py.typed`, a consumer's type checker reads every symbol
    here as `Any` — the annotations stop protecting anyone downstream, and
    nothing says so."""
    marker = resources.files("sulis_workflows") / "py.typed"
    assert marker.is_file(), "py.typed is missing from the installed package"
