"""Loader mechanics: size cap, format detection, and the PyYAML `on:` boolean trap
that would otherwise silently eat every GATE node's route table (spec §7.6)."""

from __future__ import annotations

import json

import pytest

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.model import Tool
from sulis_workflows.domain.yaml_input_limits import MAX_YAML_INPUT_BYTES

MINIMAL_TOOL_YAML = """
api_version: sulis.workflows/v1
kind: TOOL
id: echo
version: 1.0.0
title: Echo
inputs:
  value: { type: string }
output:
  value: { type: string }
controls:
  - profile: finding@1
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
effect: QUERY
"""


def test_loads_yaml() -> None:
    tool = load_definition(MINIMAL_TOOL_YAML, fmt="yaml")
    assert isinstance(tool, Tool)
    assert tool.header.id == "echo"


def test_loads_json_via_yaml_format_since_json_is_a_yaml_subset() -> None:
    doc = {
        "api_version": "sulis.workflows/v1",
        "kind": "TOOL",
        "id": "echo",
        "version": "1.0.0",
        "title": "Echo",
        "inputs": {"value": {"type": "string"}},
        "output": {"value": {"type": "string"}},
        "controls": [{"profile": "finding@1"}],
        "mechanism": {"kind": "CODE", "ref": "pkg.mod:fn"},
        "effect": "QUERY",
    }
    tool = load_definition(json.dumps(doc), fmt="json")
    assert isinstance(tool, Tool)


def test_oversize_document_is_refused_before_parsing() -> None:
    oversized = MINIMAL_TOOL_YAML + ("# " + "x" * MAX_YAML_INPUT_BYTES)
    with pytest.raises(DefinitionError) as excinfo:
        load_definition(oversized, fmt="yaml")
    assert "byte" in str(excinfo.value)


def test_non_mapping_document_is_refused() -> None:
    with pytest.raises(DefinitionError):
        load_definition("- just\n- a\n- list\n", fmt="yaml")


def test_unknown_kind_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        load_definition("api_version: sulis.workflows/v1\nkind: NOT_A_KIND\n", fmt="yaml")
    assert "kind" in str(excinfo.value)


def test_malformed_yaml_is_refused_not_raised_as_a_parser_crash() -> None:
    with pytest.raises(DefinitionError):
        load_definition("kind: TOOL\n  bad indent: [unclosed\n", fmt="yaml")


def test_bare_on_key_is_not_swallowed_as_a_yaml_1_1_boolean() -> None:
    """PyYAML's default SafeLoader resolves bare `on:` to the boolean key `True`
    (YAML 1.1). Every GATE node in this format has an `on:` mapping (spec §7.6); if
    the loader used PyYAML's default resolver, `on:` would silently vanish and every
    gate would validate as a gate with no routes at all, which is exactly the kind of
    bad-but-conformant failure the format's own principle (CLAUDE.md) asks fixtures
    to catch."""

    doc_yaml = """
api_version: sulis.workflows/v1
kind: PROCESS
id: sign-off-only
version: 1.0.0
title: Sign-off only
start: sign-off
nodes:
  sign-off:
    type: GATE
    asks: "Can this proceed?"
    on:
      PERMIT: { end: COMPLETE }
      DENY: { end: DENIED }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Not approved." }
"""
    process = load_definition(doc_yaml, fmt="yaml")
    gate = process.nodes["sign-off"]
    assert set(gate.on.keys()) == {"PERMIT", "DENY"}
    assert gate.on["PERMIT"].end == "COMPLETE"
