"""The model built from a validated document carries every field the spec names."""

from __future__ import annotations

from pathlib import Path

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.model import GateNode, RouteNode, StepNode

FIXTURES = Path(__file__).parent / "fixtures"


def test_tool_model_fields() -> None:
    tool = load_definition_file(FIXTURES / "accepted" / "tool.yaml")
    assert tool.header.id == "interrogate"
    assert tool.header.version == "1.0.0"
    assert tool.inputs["candidates"].type == "list<profile:finding@1>"
    assert tool.inputs["question"].required is True
    assert tool.output["verdict"].type == "enum[SURVIVED, DROPPED, REVISED]"
    assert tool.controls[0].kind == "profile"
    assert tool.controls[0].ref == "insight@1"
    assert tool.controls[1].kind == "conventions"
    assert tool.mechanism.kind == "SKILL"
    assert tool.mechanism.allowed_tools == ("ground-citations@1",)
    assert tool.effect == "QUERY"
    assert {e.code for e in tool.errors} == {"SOURCE_UNREACHABLE", "BRIEF_UNANSWERABLE"}


def test_profile_model_fields() -> None:
    profile = load_definition_file(FIXTURES / "accepted" / "profile.yaml")
    assert profile.header.id == "finding"
    assert profile.schema["required"] == ["id", "claim", "source"]
    assert profile.checker == "profile-conformance@1"


def test_control_model_fields() -> None:
    control = load_definition_file(FIXTURES / "accepted" / "control.yaml")
    assert control.type == "CONVENTIONS"
    assert control.applies_to == "output.insights"
    assert control.threshold is None


def test_fitness_control_threshold_fields() -> None:
    control = load_definition_file(
        FIXTURES / "accepted" / "control-fitness-with-threshold.yaml"
    )
    assert control.type == "FITNESS"
    assert control.threshold is not None
    assert control.threshold.metric == "coverage_ratio"
    assert control.threshold.op == "GTE"
    assert control.threshold.value == 0.8


def test_process_model_nodes_and_endings() -> None:
    process = load_definition_file(FIXTURES / "accepted" / "process-appendix-a.yaml")
    assert process.start == "frame"
    assert isinstance(process.nodes["frame"], StepNode)
    assert isinstance(process.nodes["choose-path"], RouteNode)
    assert isinstance(process.nodes["sign-off"], GateNode)

    route = process.nodes["after-interrogate"]
    assert isinstance(route, RouteNode)
    revised = next(opt for opt in route.when if "REVISED" in opt.if_)
    assert revised.loop is not None
    assert revised.loop.budget == 2
    assert revised.loop.on_exhausted.next == "converge"

    gate = process.nodes["sign-off"]
    assert gate.kind == "APPROVAL"
    assert [d.kind for d in gate.deciders] == ["policy", "agent", "person"]
    assert gate.deciders[2].permission == "agents.recommendation.approve"
    assert gate.on["PERMIT"].end == "COMPLETE"
    assert gate.on["DENY"].next == "gather"

    assert process.endings["COMPLETE"].outcome == "SUCCESS"
    assert process.endings["DENIED"].outcome == "STOPPED"
    assert process.state["insights"].reducer == "UPSERT_BY_ID"
    assert process.state["insights"].key == "id"


def test_gate_kind_defaults_to_approval_when_absent() -> None:
    process = load_definition_file(FIXTURES / "accepted" / "process-appendix-a.yaml")
    # sign-off declares kind explicitly; build a second doc without it to check the default.
    from sulis_workflows.definition.load import load_definition

    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: implicit-approval
version: 1.0.0
title: Implicit approval
start: gate
nodes:
  gate:
    type: GATE
    asks: "Proceed?"
    on:
      PERMIT: { end: COMPLETE }
      DENY: { end: DENIED }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
"""
    implicit = load_definition(doc, fmt="yaml")
    assert implicit.nodes["gate"].kind == "APPROVAL"
    assert process is not None  # keep both fixtures exercised
