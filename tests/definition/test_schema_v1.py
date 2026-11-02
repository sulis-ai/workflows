"""V1 — schema conformance (spec §1.4 closed objects, §1.5 SCREAMING_SNAKE_CASE).

WP-01 A1: every rule gets at least one accepted and one refused fixture, and the
refusal names the rule. WP-01 A3 supplies the bad-but-conformant cases for V1: a
plausible extra field, a value that "looks like" the right type but has the wrong
case, an id that merely looks like a string but isn't kebab-case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.load import load_definition, load_definition_file
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


# ------------------------------------------------------------- step session (D49) --
# V1 refuses `session` on main too, as an unknown field of the node, and V1's own message
# stops at the node (`$defs/node` is a `oneOf`). So these also read the fault from
# `node_step` itself: it must lie INSIDE the session, proving the shape, not that accident.

_PROCESS_SCHEMA = (
    Path(__file__).parents[2]
    / "src/sulis_workflows/definition/schema/process.v1.schema.json"
)


def _faults_in_step(node: dict) -> list[str]:
    defs = json.loads(_PROCESS_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    validator = Draft202012Validator({"$ref": "#/$defs/node_step", "$defs": defs})
    return [
        "/".join(str(p) for p in e.absolute_path) for e in validator.iter_errors(node)
    ]


@pytest.mark.parametrize(
    "fixture, location",
    [
        ("unknown-key", "session"),
        ("missing-sees", "session"),
        ("agent-two-keys", "session/agent"),
        ("lowercase-mode", "session/mode"),
        ("duplicate-sees", "session/sees"),
        ("too-many-sees", "session/sees"),
    ],
)
def test_session_fixture_refused_at_its_own_fault(fixture: str, location: str) -> None:
    path = FIXTURES / "refused" / f"process-step-session-{fixture}.yaml"
    with pytest.raises(DefinitionError) as excinfo:
        load_definition_file(path)
    assert excinfo.value.rule == "V1"
    assert "nodes/step" in excinfo.value.message
    node = yaml.safe_load(path.read_text(encoding="utf-8"))["nodes"]["step"]
    assert _faults_in_step(node) == [location]


def test_session_schema_matches_the_decision() -> None:
    defs = json.loads(_PROCESS_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    session = defs["node_step"]["properties"]["session"]
    assert session["type"] == "object"
    assert session["additionalProperties"] is False
    assert sorted(session["required"]) == ["agent", "mode", "model_role", "sees"]
    props = session["properties"]
    assert props["mode"]["enum"] == ["CONTINUE_IF_LOCAL", "FRESH"]
    assert props["model_role"]["enum"] == ["JUDGEMENT", "BUILD"]
    assert props["sees"]["items"]["pattern"] == "^[a-z][a-z0-9-]*$"
    assert props["sees"]["uniqueItems"] is True
    assert props["sees"]["maxItems"] == 20
    assert "minItems" not in props["sees"]
    forms = {tuple(form["required"]): form for form in props["agent"]["oneOf"]}
    assert set(forms) == {("same",), ("kind",), ("different_from",)}
    assert all(form["additionalProperties"] is False for form in forms.values())
    assert forms[("same",)]["properties"]["same"]["const"] is True
    assert forms[("kind",)]["properties"]["kind"]["pattern"] == "^[a-z][a-z0-9_-]*$"
    assert forms[("different_from",)]["properties"]["different_from"]["minLength"] == 1


def _process_with_session(session: str) -> str:
    return f"""
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: step
nodes:
  step: {{ type: STEP, tool: t@1, in: {{}}, out: {{}}, session: {session}, end: DONE }}
endings:
  DONE: {{ outcome: SUCCESS, says: "Done." }}
"""


def test_session_edge_values_are_refused_or_accepted() -> None:
    accepted = _process_with_session(
        "{ mode: FRESH, agent: { same: true }, model_role: BUILD, sees: [] }"
    )
    assert load_definition(accepted).nodes["step"].session.sees == ()
    for agent in (
        "{ same: false }",
        "{}",
        '{ different_from: "" }',
        "{ kind: Not-A-Slug }",
    ):
        doc = _process_with_session(
            "{ mode: FRESH, agent: " + agent + ", model_role: BUILD, sees: [] }"
        )
        with pytest.raises(DefinitionError) as excinfo:
            load_definition(doc)
        assert excinfo.value.rule == "V1"
        node = yaml.safe_load(doc)["nodes"]["step"]
        assert _faults_in_step(node) == ["session/agent"]
