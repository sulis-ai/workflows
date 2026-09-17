"""V1 — schema conformance (spec §1.4 closed objects, §1.5 SCREAMING_SNAKE_CASE).

WP-01 A1: every rule gets at least one accepted and one refused fixture, and the
refusal names the rule. WP-01 A3 supplies the bad-but-conformant cases for V1: a
plausible extra field, a value that "looks like" the right type but has the wrong
case, an id that merely looks like a string but isn't kebab-case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.model import Control, Process, Profile, Tool

FIXTURES = Path(__file__).parent / "fixtures"
ACCEPTED = sorted((FIXTURES / "accepted").glob("*.yaml"))
REFUSED = sorted((FIXTURES / "refused").glob("*.yaml"))

_MODEL_TYPE_BY_KIND = {
    "PROFILE": Profile,
    "TOOL": Tool,
    "CONTROL": Control,
    "PROCESS": Process,
}


@pytest.mark.parametrize("path", ACCEPTED, ids=lambda p: p.stem)
def test_accepted_fixture_loads(path: Path) -> None:
    definition = load_definition_file(path)
    kind = definition.header.kind
    assert isinstance(definition, _MODEL_TYPE_BY_KIND[kind])


@pytest.mark.parametrize("path", REFUSED, ids=lambda p: p.stem)
def test_refused_fixture_is_refused_by_v1(path: Path) -> None:
    with pytest.raises(DefinitionError) as excinfo:
        load_definition_file(path)
    assert excinfo.value.rule == "V1"
    # `kind` itself being wrong (missing, or not one of the four) is refused before a
    # schema can even be chosen, so schema_path is legitimately absent only there.
    if excinfo.value.schema_path is not None:
        assert Path(excinfo.value.schema_path).exists()


def test_refusal_for_a_recognised_kind_names_its_schema_path() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        load_definition_file(FIXTURES / "refused" / "tool-unknown-field.yaml")
    assert excinfo.value.schema_path is not None
    assert excinfo.value.schema_path.endswith("tool.v1.schema.json")
    assert Path(excinfo.value.schema_path).exists()


def test_at_least_one_accepted_and_one_refused_fixture_exists() -> None:
    assert len(ACCEPTED) >= 1
    assert len(REFUSED) >= 1


def test_unknown_top_level_field_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        load_definition_file(FIXTURES / "refused" / "tool-unknown-field.yaml")
    assert "experimental_hint" in str(excinfo.value)


def test_lowercase_enum_member_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        load_definition_file(FIXTURES / "refused" / "tool-lowercase-enum-type.yaml")
    assert excinfo.value.rule == "V1"
