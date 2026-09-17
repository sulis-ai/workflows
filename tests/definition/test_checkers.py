"""The two built-in checkers (spec §5.2, §7.6). Beyond V3's structural "ships a
passing and a failing example" check, this runs each Tool's declared examples
through the real Python function and confirms the result actually matches what
the Tool document claims — an example that lied about its own checker would
still pass V3's structural check but fail here."""

from __future__ import annotations

from pathlib import Path

from sulis_workflows.definition.checkers import decision_evidence, profile_conformance
from sulis_workflows.definition.load import load_definition, load_definition_file
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import validate_tool

BUILTIN = Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition" / "builtin"

_FINDING_PROFILE = """
api_version: sulis.workflows/v1
kind: PROFILE
id: finding
version: 1.0.0
title: Finding
grounded_in: "W3C PROV-O prov:wasDerivedFrom"
schema:
  type: object
  required: [id, claim, source]
  properties:
    id: { type: string }
    claim: { type: string, minLength: 10 }
    source: { type: string }
  additionalProperties: false
"""


def _registry_with_finding_profile() -> Registry:
    return Registry([load_definition_file(BUILTIN / "control-result.profile.yaml"), load_definition(_FINDING_PROFILE)])


def test_profile_conformance_tool_has_no_v3_findings() -> None:
    tool = load_definition_file(BUILTIN / "profile-conformance.tool.yaml")
    registry = Registry([load_definition_file(BUILTIN / "control-result.profile.yaml")])
    findings = [f for f in validate_tool(tool, registry) if f.rule == "V3"]
    assert findings == []


def test_profile_conformance_examples_actually_match_the_real_function() -> None:
    tool = load_definition_file(BUILTIN / "profile-conformance.tool.yaml")
    registry = _registry_with_finding_profile()
    for example in tool.examples:
        result = profile_conformance(example.inputs["value"], example.inputs["control"], registry=registry)
        assert result["passed"] == example.expect["result"]["passed"], example.name


def test_decision_evidence_tool_has_no_v3_findings() -> None:
    tool = load_definition_file(BUILTIN / "decision-evidence.tool.yaml")
    registry = Registry([load_definition_file(BUILTIN / "control-result.profile.yaml")])
    findings = [f for f in validate_tool(tool, registry) if f.rule == "V3"]
    assert findings == []


def test_decision_evidence_examples_actually_match_the_real_function() -> None:
    tool = load_definition_file(BUILTIN / "decision-evidence.tool.yaml")
    for example in tool.examples:
        result = decision_evidence(
            example.inputs["value"], example.inputs["control"], example.inputs["reviewing"]
        )
        assert result["passed"] == example.expect["result"]["passed"], example.name


def test_profile_conformance_directly() -> None:
    registry = _registry_with_finding_profile()
    good = {"id": "f1", "claim": "this is a long enough claim", "source": "obs"}
    assert profile_conformance(good, "finding@1", registry=registry)["passed"] is True

    bad = {"id": "f1", "claim": "short"}
    result = profile_conformance(bad, "finding@1", registry=registry)
    assert result["passed"] is False
    assert result["findings"]


def test_decision_evidence_directly() -> None:
    reviewing = ["state.recommendations"]
    good = {"verdict": "PERMIT", "rationale": "ok", "evidence": [{"path": "state.recommendations", "claim": "x"}]}
    assert decision_evidence(good, "decision@1", reviewing)["passed"] is True

    bad = {"verdict": "PERMIT", "rationale": "ok", "evidence": [{"path": "state.notes", "claim": "x"}]}
    result = decision_evidence(bad, "decision@1", reviewing)
    assert result["passed"] is False
    assert "state.notes" in result["findings"][0]["message"]
