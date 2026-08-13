"""Proves `route_decider` actually resolves as a real step dispatch AND wires a conditional
edge off its OWN computed output -- the seam `VALID_NODE_TYPES` declared but nothing ever
implemented (NodeResolver had no branch for it, `_wire_edges` only recognised "routing", GV-01
didn't count it as a cycle-breaking type). A `route_decider` node computes its routing value via
a real step dispatch (writing `step_outputs[node.id]`, exactly like an ordinary step node) and
`OutcomeGraphBuilder._wire_edges` reads that SAME node's own output back to pick a conditional
edge -- one node, two engine-recognised effects, no id-collision problem a separate
"decider + routing" node pair would otherwise have (DAGNode ids must be globally unique).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.identity import AdapterIdentity
from sulis_workflows.domain.ports.base import stub_identity
from sulis_workflows.runtime.adapters import Adapters


@dataclass
class _RouteStubToolDispatch:
    """A minimal ToolDispatchPort double: `produce_verdict` returns a fixed verdict (so a test
    can control what the upstream step "found"); `decide` reads that verdict back off
    `step_outputs[source_key]` and returns `{"route": <verdict>}` -- exactly the shape a real
    guard-evaluator primitive (e.g. brain_runtime_runner's `evaluate_transition_guards`) would
    produce. Proves route_decider's own conditional edge genuinely reads a value THIS node
    computed at execution time, not something baked into the DAG statically."""

    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="_RouteStubToolDispatch", port_name="ToolDispatchPort")

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def invoke(self, primitive, args, *, sandbox_root, platform_id, run_id, step_outputs=None):
        if primitive == "produce_verdict":
            return {"verdict": args["verdict"]}
        if primitive == "decide":
            # Mirrors evaluate_transition_guards' real semantics: a finite, named checklist of
            # guards, falling through to the explicit "continue" key when none match -- never
            # echoing an arbitrary upstream value verbatim (that's what let this test's first
            # draft slip past the "no match -> silently picks the first route" risk the plan
            # calls out: an unmatched "ok" verdict isn't a key in `routes` at all, so
            # make_routing_edge fell back to whichever route happened to be inserted first).
            upstream = (step_outputs or {}).get(args["source_key"]) or {}
            return {"route": "blocked" if upstream.get("verdict") == "blocked" else "continue"}
        raise AssertionError(f"unexpected primitive: {primitive}")


def _dag():
    return {"flow": {"dag": {"nodes": [
        {"id": "a", "type": "step", "spec_ref": "spec/a"},
        {"id": "a__route", "type": "route_decider", "depends_on": ["a"], "spec_ref": "spec/route",
         "config": {"routes": {"blocked": "a__terminal-blocked", "continue": "b"}}},
        {"id": "a__terminal-blocked", "type": "step", "depends_on": ["a__route"], "spec_ref": "spec/terminal"},
        {"id": "b", "type": "step", "depends_on": ["a__route"], "spec_ref": "spec/b"},
    ]}}}


def _steps(verdict: str) -> dict:
    return {
        "spec/a": {"primitive": "produce_verdict", "args": {"verdict": verdict}},
        "spec/route": {"primitive": "decide", "args": {"source_key": "a"}},
        "spec/terminal": {},
        "spec/b": {},
    }


def _compile(verdict: str):
    spec_repo = MemorySpecRepository(dags=_dag(), steps=_steps(verdict), sequences={})
    adapters = Adapters(tool_dispatch=_RouteStubToolDispatch(), sandbox_root="/tmp")
    return OutcomeGraphCompiler(spec_repo=spec_repo, adapters=adapters).compile(outcome_id="flow")


def test_route_decider_branches_to_the_matching_route_when_the_guard_trips():
    graph = _compile("blocked")
    result = asyncio.run(graph.ainvoke({"step_outputs": {}}))
    assert "a__terminal-blocked" in result["completed_nodes"]
    assert "b" not in result["completed_nodes"]


def test_route_decider_falls_through_to_continue_when_the_guard_does_not_trip():
    graph = _compile("ok")
    result = asyncio.run(graph.ainvoke({"step_outputs": {}}))
    assert "b" in result["completed_nodes"]
    assert "a__terminal-blocked" not in result["completed_nodes"]


def test_route_decider_itself_appears_in_completed_nodes_as_a_real_dispatch():
    # Not a bare passthrough (unlike "routing"/"fan_out"/"for_each"/"while") -- it really ran.
    graph = _compile("blocked")
    result = asyncio.run(graph.ainvoke({"step_outputs": {}}))
    assert "a__route" in result["completed_nodes"]
    assert result["step_outputs"]["a__route"] == {"route": "blocked"}


def test_route_decider_mediated_cycle_passes_gv01_unbounded_cycle_check():
    """A route_decider whose own route targets an ANCESTOR (a genuine backward edge, mirroring a
    real deliver<->prove respiral) must be recognised as a conditional exit path by GV-01 --
    previously only "routing"/"fan_out"/"while" were, so this exact shape (a real cycle-back edge)
    would have hard-failed compilation as an unbounded cycle. `start` is the real root feeding
    `deliver`'s first entry; `deliver` is re-entered a second way via the cycle-back edge -- this
    test only asserts COMPILATION succeeds (a structural/GV-01 proof), not full cyclic execution."""
    dag = {"flow": {"dag": {"nodes": [
        {"id": "start", "type": "step", "spec_ref": "spec/start"},
        {"id": "deliver", "type": "step", "depends_on": ["start", "prove__route"], "spec_ref": "spec/deliver"},
        {"id": "prove", "type": "step", "depends_on": ["deliver"], "spec_ref": "spec/prove"},
        {"id": "prove__route", "type": "route_decider", "depends_on": ["prove"], "spec_ref": "spec/route",
         "config": {"routes": {"cycle-back": "deliver", "continue": "publish"}}},
        {"id": "publish", "type": "step", "depends_on": ["prove__route"], "spec_ref": "spec/publish"},
    ]}}}
    steps = {
        "spec/start": {},
        "spec/deliver": {},
        "spec/prove": {"primitive": "produce_verdict", "args": {"verdict": "cycle-back"}},
        "spec/route": {"primitive": "decide", "args": {"source_key": "prove"}},
        "spec/publish": {},
    }
    spec_repo = MemorySpecRepository(dags=dag, steps=steps, sequences={})
    adapters = Adapters(tool_dispatch=_RouteStubToolDispatch(), sandbox_root="/tmp")
    # Must not raise GraphValidationError("GV-01: Unbounded cycle detected: ...").
    compiled = OutcomeGraphCompiler(spec_repo=spec_repo, adapters=adapters).compile(outcome_id="flow")
    assert compiled is not None
