"""V3-V15 — the cross-cutting validator rules (spec §14). Each rule gets at least
one accepted and one refused fixture; WP-01 A3's bad-but-conformant cases are
marked where they apply."""

from __future__ import annotations

from pathlib import Path

from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import Finding, validate

_FIXTURES = Path(__file__).parent / "fixtures"


def _load(text: str):
    return load_definition(text, fmt="yaml")


def _rules(findings: list[Finding]) -> set[str]:
    return {f.rule for f in findings}


ECHO_TOOL = """
api_version: sulis.workflows/v1
kind: TOOL
id: echo
version: 1.0.0
title: Echo
inputs:
  value: { type: string }
output:
  value: { type: string }
controls: [ { profile: finding@1 } ]
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
effect: QUERY
"""


def _base_registry(*extra_yaml: str) -> Registry:
    return Registry([_load(ECHO_TOOL), *[_load(y) for y in extra_yaml]])


# ------------------------------------------------------------------------------ V3 --


def test_v3_accepted_tool_has_a_control() -> None:
    findings = validate(ECHO_TOOL, registry=_base_registry())
    assert "V3" not in _rules(findings)


def test_v3_refused_tool_with_no_controls() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: no-controls
version: 1.0.0
title: No controls
inputs: { value: { type: string } }
output: { value: { type: string } }
controls: []
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
effect: QUERY
"""
    findings = validate(doc, registry=_base_registry())
    assert "V3" in _rules(findings)


def test_v3_refused_agentic_tool_with_only_a_policy_control() -> None:
    """A3 bad-but-conformant: the tool has a control (so a naive "has controls"
    check passes), but it's the one kind that never checks the output itself."""

    policy_control = """
api_version: sulis.workflows/v1
kind: CONTROL
id: may-run
version: 1.0.0
type: POLICY
title: May this run
"""
    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: interrogate
version: 1.0.0
title: Interrogate
inputs: { question: { type: string } }
output: { verdict: { type: "enum[SURVIVED, DROPPED]" } }
controls: [ { policy: may-run@1 } ]
mechanism: { kind: SKILL, ref: skills/interrogate }
effect: QUERY
"""
    findings = validate(doc, registry=_base_registry(policy_control))
    assert "V3" in _rules(findings)


def test_v3_refused_checker_with_only_passing_examples() -> None:
    """A3 bad-but-conformant: a checker that always passes would satisfy a naive
    'has examples' check."""

    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: always-passes
version: 1.0.0
title: Always passes
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
checker_for: { control: PROFILE }
inputs: { value: { type: any }, control: { type: string } }
output: { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
effect: QUERY
examples:
  - { name: "passes", inputs: { value: {}, control: "x@1" }, expect: { result: { passed: true } } }
  - { name: "also passes", inputs: { value: {}, control: "x@1" }, expect: { result: { passed: true } } }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V3" in _rules(findings)


def test_v3_accepted_checker_with_passing_and_failing_examples() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: real-checker
version: 1.0.0
title: Real checker
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
checker_for: { control: PROFILE }
inputs: { value: { type: any }, control: { type: string } }
output: { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
effect: QUERY
examples:
  - { name: "passes", inputs: { value: {}, control: "x@1" }, expect: { result: { passed: true } } }
  - { name: "fails", inputs: { value: {}, control: "x@1" }, expect: { result: { passed: false } } }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V3" not in _rules(findings)


def test_v3_refused_checker_with_only_passing_examples_even_without_checker_for() -> (
    None
):
    """spec §5.2 defines a checker by what it returns, not by declaring
    `checker_for` — a specific checker wired through a Profile's own `checker:`
    field (like decision-evidence@1) still owes the pass+fail requirement."""

    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: specific-checker
version: 1.0.0
title: Specific checker
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
inputs: { value: { type: any }, control: { type: string } }
output: { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
effect: QUERY
examples:
  - { name: "passes", inputs: { value: {}, control: "x@1" }, expect: { result: { passed: true } } }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V3" in _rules(findings)


def test_v3_refused_non_policy_control_with_no_checker() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: CONTROL
id: some-conventions
version: 1.0.0
type: CONVENTIONS
title: Some conventions
applies_to: output.value
"""
    findings = validate(doc, registry=Registry())
    assert "V3" in _rules(findings)


# ------------------------------------------------------------------------------ V4 --

_INTERROGATE_TOOL = """
api_version: sulis.workflows/v1
kind: TOOL
id: interrogate
version: 1.0.0
title: Interrogate
inputs:
  question: { type: string }
output:
  verdict: { type: "enum[SURVIVED, DROPPED]" }
controls: [ { profile: finding@1 } ]
mechanism: { kind: SKILL, ref: skills/interrogate }
effect: QUERY
"""


def _process_with_step(step_yaml: str, *, extra_state: str = "") -> str:
    return f"""
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
inputs:
  question: {{ type: string }}
state:
  verdict: {{ type: "enum[SURVIVED, DROPPED]", reducer: REPLACE }}
{extra_state}
start: step
nodes:
  step:
{step_yaml}
endings:
  DONE: {{ outcome: SUCCESS, says: "Done." }}
"""


def test_v4_refused_unmapped_required_input() -> None:
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: {}, out: { verdict: state.verdict }, end: DONE }"
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V4" in _rules(findings)


def test_v4_accepted_mapped_required_input() -> None:
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, "
        "out: { verdict: state.verdict }, end: DONE }"
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V4" not in _rules(findings)


def test_v4_refused_type_mismatch_in_out_mapping() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  count: { type: integer, reducer: REPLACE }
start: step
nodes:
  step:
    { type: STEP, tool: interrogate@1, in: { question: "state.count" }, out: { verdict: state.count }, end: DONE }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V4" in _rules(findings)


# ------------------------------------------------------------------------------ V5 --


def test_v5_accepted_expression() -> None:
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, out: { verdict: state.verdict },\n"
        "      precondition: 'state.verdict == \"SURVIVED\"', end: DONE }"
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V5" not in _rules(findings)


def test_v5_refused_enum_compared_outside_its_values() -> None:
    """A3 bad-but-conformant: the named V5 example verbatim."""

    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, out: { verdict: state.verdict },\n"
        "      precondition: 'state.verdict == \"MAYBE\"', end: DONE }"
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V5" in _rules(findings)


def test_v5_refused_unparseable_expression() -> None:
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, out: { verdict: state.verdict },\n"
        "      precondition: 'state.verdict ==', end: DONE }"
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V5" in _rules(findings)


# ------------------------------------------------------------------------------ V6 --

_ROUTE_PROCESS = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  verdict: { type: "enum[SURVIVED, DROPPED]", reducer: REPLACE }
start: route
nodes:
  route:
    type: ROUTE
    when:
__WHEN__
endings:
  SURVIVED_END: { outcome: SUCCESS, says: "Survived." }
  DROPPED_END: { outcome: SUCCESS, says: "Dropped." }
"""


def _route_process(when: str) -> str:
    return _ROUTE_PROCESS.replace("__WHEN__", when)


def test_v6_accepted_exhaustive_route_needs_no_otherwise() -> None:
    doc = _route_process(
        "      - { if: 'state.verdict == \"SURVIVED\"', end: SURVIVED_END }\n"
        "      - { if: 'state.verdict == \"DROPPED\"', end: DROPPED_END }"
    )
    findings = validate(doc, registry=Registry())
    assert "V6" not in _rules(findings)


def test_v6_refused_route_missing_one_enum_value_and_no_otherwise() -> None:
    """A3 bad-but-conformant: looks exhaustive (every branch is a clean enum ==
    literal test) but SURVIVED is never covered."""

    doc = _route_process(
        "      - { if: 'state.verdict == \"DROPPED\"', end: DROPPED_END }"
    )
    findings = validate(doc, registry=Registry())
    assert "V6" in _rules(findings)


def test_v6_accepted_route_with_otherwise() -> None:
    doc = _route_process(
        "      - { if: 'state.verdict == \"DROPPED\"', end: DROPPED_END }\n    otherwise: { end: SURVIVED_END }"
    )
    findings = validate(doc, registry=Registry())
    assert "V6" not in _rules(findings)


# ------------------------------------------------------------------------------ V7 --


def test_v7_accepted_all_nodes_reachable_and_can_end() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, next: b }
  b: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V7" not in _rules(findings)


def test_v7_refused_unreachable_node() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
  orphan: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V7" in _rules(findings)
    assert any(f.node == "orphan" for f in findings if f.rule == "V7")


def test_v7_refused_node_with_no_way_to_end() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, next: b }
  b: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, next: a }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V7" in _rules(findings)


# ------------------------------------------------------------------------------ V8 --


def test_v8_accepted_positive_loop_budget() -> None:
    doc = _route_process(
        "      - { if: 'state.verdict == \"SURVIVED\"', end: SURVIVED_END }\n"
        "      - { if: 'state.verdict == \"DROPPED\"', next: route, loop: { budget: 3 } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V8" not in _rules(findings)


def test_v8_refused_zero_loop_budget() -> None:
    doc = _route_process(
        "      - { if: 'state.verdict == \"SURVIVED\"', end: SURVIVED_END }\n"
        "      - { if: 'state.verdict == \"DROPPED\"', next: route, loop: { budget: 0 } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V8" in _rules(findings)


def test_v8_accepted_route_loop_counts_passes() -> None:
    doc = _route_process(
        "      - { if: 'state.verdict == \"SURVIVED\"', end: SURVIVED_END }\n"
        "      - { if: 'state.verdict == \"DROPPED\"', next: route, "
        "loop: { budget: 3, counts: PASSES } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V8" not in _rules(findings)


def test_v8_refused_route_loop_counts_failures() -> None:
    """D33: a ROUTE's own `when` branch is an arbitrary state expression —
    unlike a GATE's own DENY verdict, there is no engine-visible signal for
    "this branch was taken because a check failed", so `counts: FAILURES`
    is refused rather than guessed at."""
    doc = _route_process(
        "      - { if: 'state.verdict == \"SURVIVED\"', end: SURVIVED_END }\n"
        "      - { if: 'state.verdict == \"DROPPED\"', next: route, "
        "loop: { budget: 3, counts: FAILURES } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V8" in _rules(findings)


# ------------------------------------------------------------------------------ V9 --

_GATE_PROCESS = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: gate
nodes:
  gate:
__GATE_BODY__
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
"""


def _gate_process(gate_body: str) -> str:
    return _GATE_PROCESS.replace("__GATE_BODY__", gate_body)


def test_v9_accepted_gate_with_permit_and_deny() -> None:
    doc = _gate_process(
        '    { type: GATE, asks: "Proceed?", on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }'
    )
    findings = validate(doc, registry=Registry())
    assert "V9" not in _rules(findings)


def test_v9_refused_gate_with_no_asks() -> None:
    doc = _gate_process(
        "    { type: GATE, on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


def test_v9_refused_permit_with_no_route() -> None:
    doc = _gate_process(
        '    { type: GATE, asks: "Proceed?", on: { DENY: { end: DENIED } } }'
    )
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


def test_v9_refused_indeterminate_with_a_route() -> None:
    """A3 bad-but-conformant: INDETERMINATE must never route."""

    doc = _gate_process(
        '    { type: GATE, asks: "Proceed?", on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED }, '
        "INDETERMINATE: { end: DENIED } } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


def test_v9_refused_unknown_gate_kind() -> None:
    doc = _gate_process(
        '    { type: GATE, kind: MAYBE, asks: "Proceed?", on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }'
    )
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


def test_v9_refused_input_gate_not_yet_supported() -> None:
    """WP-03a Fault 2: `kind: INPUT` is spec-legal (§7.6) but this engine
    does not implement it yet — `_advance_gate` never reads `node.kind`,
    `answer_type`, `answer_into` or the `ANSWERED` verdict, so a validated
    INPUT gate crashed at runtime instead ("no route declared for verdict
    'PERMIT'"). Refused at validation time instead of only failing when
    someone actually runs it — even a fully well-formed INPUT gate (a
    real `answer_type`/`answer_into`, an `ANSWERED` route) is refused,
    since the refusal is about engine support, not gate shape."""
    doc = _gate_process(
        '    { type: GATE, kind: INPUT, asks: "What is the target date?", '
        "answer_type: string, answer_into: state.target_date, on: { ANSWERED: { end: COMPLETE } } }"
    )
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


def test_v9_refused_person_required_when_with_no_person_decider() -> None:
    doc = _gate_process(
        '    { type: GATE, asks: "Proceed?", deciders: [ { policy: may-run@1 } ],\n'
        "      person_required_when: \"inputs.x == 'y'\",\n"
        "      on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }"
    )
    policy_control = """
api_version: sulis.workflows/v1
kind: CONTROL
id: may-run
version: 1.0.0
type: POLICY
title: May this run
"""
    findings = validate(doc, registry=_base_registry(policy_control))
    assert "V9" in _rules(findings)


def test_v9_refused_agent_decider_not_returning_decision_profile() -> None:
    bad_agent = """
api_version: sulis.workflows/v1
kind: TOOL
id: reviewer
version: 1.0.0
title: Reviewer
inputs: { criteria: { type: string } }
output: { note: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism: { kind: SKILL, ref: skills/reviewer }
effect: QUERY
"""
    doc = _gate_process(
        '    { type: GATE, asks: "Proceed?", deciders: [ { agent: reviewer@1 } ],\n'
        "      on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }"
    )
    findings = validate(doc, registry=_base_registry(bad_agent))
    assert "V9" in _rules(findings)


def test_v9_refused_agent_decider_reviewing_its_own_output() -> None:
    """No deciding on your own work (ANSI INCITS 359-2004, static separation of duty)."""

    recommend_tool = """
api_version: sulis.workflows/v1
kind: TOOL
id: recommend
version: 1.0.0
title: Recommend
inputs: { question: { type: string } }
output: { decision: { type: "profile:decision@1" } }
controls: [ { profile: finding@1 } ]
mechanism: { kind: SKILL, ref: skills/recommend }
effect: QUERY
"""
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  recommendations: { type: string, reducer: REPLACE }
start: recommend-step
nodes:
  recommend-step:
    { type: STEP, tool: recommend@1, in: { question: inputs.x }, out: { decision: state.recommendations },
      next: gate }
  gate:
    { type: GATE, asks: "Proceed?", deciders: [ { agent: recommend@1 } ], reviewing: [state.recommendations],
      on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }
inputs: { x: { type: string } }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
"""
    findings = validate(doc, registry=_base_registry(recommend_tool))
    assert "V9" in _rules(findings)


def test_v9_accepted_note_into_a_replace_channel() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  note: { type: string, reducer: REPLACE, default: "" }
start: gate
nodes:
  gate:
    { type: GATE, asks: "Proceed?", note_into: state.note,
      on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
"""
    findings = validate(doc, registry=Registry())
    assert "V9" not in _rules(findings)


def test_v9_refused_note_into_an_append_channel() -> None:
    """D27: `_state_with_note` recomputes and re-applies the gate's note on
    every replay pass — safe for REPLACE (idempotent), not for APPEND, which
    would accumulate the same note again each time the run is replayed."""

    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  notes: { type: "list<string>", reducer: APPEND, default: [] }
start: gate
nodes:
  gate:
    { type: GATE, asks: "Proceed?", note_into: state.notes,
      on: { PERMIT: { end: COMPLETE }, DENY: { end: DENIED } } }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
"""
    findings = validate(doc, registry=Registry())
    assert "V9" in _rules(findings)


# ------------------------------------------------------------------------------ V10 --

_CHILD_PROCESS = """
api_version: sulis.workflows/v1
kind: PROCESS
id: child
version: 1.0.0
title: Child
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: CHILD_DONE }
inputs: { x: { type: string } }
endings:
  CHILD_DONE: { outcome: SUCCESS, says: "Child done." }
"""

_CALL_CHILD_TOOL_FULLY_MAPPED = """
api_version: sulis.workflows/v1
kind: TOOL
id: call-child
version: 1.0.0
title: Call child
inputs: { x: { type: string } }
output: { ending: { type: "enum[CHILD_DONE, ESCALATED, FAILED, FORBIDDEN, CANCELLED]" } }
controls: [ { profile: finding@1 } ]
mechanism:
  kind: PROCESS
  ref: child@1
  inputs: { x: x }
  result:
    endings: { CHILD_DONE: CHILD_DONE, ESCALATED: ESCALATED, FAILED: FAILED, FORBIDDEN: FORBIDDEN, CANCELLED: CANCELLED }
effect: QUERY
"""

_CALL_CHILD_TOOL_MISSING_FORBIDDEN = """
api_version: sulis.workflows/v1
kind: TOOL
id: call-child
version: 1.0.0
title: Call child
inputs: { x: { type: string } }
output: { ending: { type: "enum[CHILD_DONE, ESCALATED, FAILED, FORBIDDEN, CANCELLED]" } }
controls: [ { profile: finding@1 } ]
mechanism:
  kind: PROCESS
  ref: child@1
  inputs: { x: x }
  result:
    endings: { CHILD_DONE: CHILD_DONE, ESCALATED: ESCALATED, FAILED: FAILED, CANCELLED: CANCELLED }
effect: QUERY
"""


def _parent_process_calling_child() -> str:
    return """
api_version: sulis.workflows/v1
kind: PROCESS
id: parent
version: 1.0.0
title: Parent
state:
  ending: { type: string, reducer: REPLACE }
start: call
nodes:
  call: { type: STEP, tool: call-child@1, in: { x: inputs.x }, out: { ending: state.ending }, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""


def test_v10_accepted_call_mapping_every_child_ending() -> None:
    doc = _parent_process_calling_child()
    registry = _base_registry(_CHILD_PROCESS, _CALL_CHILD_TOOL_FULLY_MAPPED)
    findings = validate(doc, registry=registry)
    assert "V10" not in _rules(findings)


def test_v10_refused_call_missing_forbidden_ending() -> None:
    """A3 bad-but-conformant: every ending except FORBIDDEN is mapped."""

    doc = _parent_process_calling_child()
    registry = _base_registry(_CHILD_PROCESS, _CALL_CHILD_TOOL_MISSING_FORBIDDEN)
    findings = validate(doc, registry=registry)
    assert "V10" in _rules(findings)


_SELF_CALL_TOOL = """
api_version: sulis.workflows/v1
kind: TOOL
id: call-self
version: 1.0.0
title: Call self
inputs: { x: { type: string } }
output: { ending: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism: { kind: PROCESS, ref: recursive@1, inputs: { x: x } }
effect: QUERY
"""


def test_v10_refused_self_reachable_call_with_no_on_depth_exhausted() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: recursive
version: 1.0.0
title: Recursive
start: call
nodes:
  call: { type: STEP, tool: call-self@1, in: { x: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    registry = _base_registry(_SELF_CALL_TOOL, doc)
    findings = validate(doc, registry=registry)
    assert "V10" in _rules(findings)


def test_v10_accepted_self_reachable_call_with_on_depth_exhausted() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: recursive
version: 1.0.0
title: Recursive
start: call
nodes:
  call:
    { type: STEP, tool: call-self@1, in: { x: inputs.x }, out: {}, end: DONE,
      on_depth_exhausted: { end: DONE } }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    registry = _base_registry(_SELF_CALL_TOOL, doc)
    findings = validate(doc, registry=registry)
    assert "V10" not in _rules(findings)


# ------------------------------------------------------------------------------ V11 --


def test_v11_accepted_parallel_branches_write_different_channels() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  a_out: { type: string, reducer: REPLACE }
  b_out: { type: string, reducer: REPLACE }
start: par
nodes:
  par: { type: PARALLEL, branches: [a, b], join: joined }
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: { value: state.a_out }, next: joined }
  b: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: { value: state.b_out }, next: joined }
  joined: { type: JOIN, next: done }
  done: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V11" not in _rules(findings)


def test_v11_refused_two_branches_writing_one_replace_channel() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  shared: { type: string, reducer: REPLACE }
start: par
nodes:
  par: { type: PARALLEL, branches: [a, b], join: joined }
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: { value: state.shared }, next: joined }
  b: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: { value: state.shared }, next: joined }
  joined: { type: JOIN, next: done }
  done: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V11" in _rules(findings)


def test_v11_refused_join_not_reachable_from_a_branch() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: par
nodes:
  par: { type: PARALLEL, branches: [a, b], join: joined }
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, next: joined }
  b: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
  joined: { type: JOIN, next: done }
  done: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V11" in _rules(findings)


# ------------------------------------------------------------------------------ V12 --


def test_v12_accepted_for_each_over_a_list() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  items: { type: "list<string>", reducer: REPLACE }
start: fe
nodes:
  fe: { type: FOR_EACH, over: state.items, as: item, do: work, next: done }
  work: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
  done: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V12" not in _rules(findings)


def test_v12_refused_for_each_over_a_non_list() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  count: { type: integer, reducer: REPLACE }
start: fe
nodes:
  fe: { type: FOR_EACH, over: state.count, as: item, do: work, next: done }
  work: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
  done: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V12" in _rules(findings)


# ------------------------------------------------------------------------------ V13 --


def test_v13_accepted_destructive_step_with_precondition() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a:
    { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE,
      destructive: true, precondition: "exists(inputs.x)" }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V13" not in _rules(findings)


def test_v13_refused_destructive_step_with_no_precondition() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE, destructive: true }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V13" in _rules(findings)


# ------------------------------------------------------------------------------ V14 --


def test_v14_accepted_ending_has_says() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V14" not in _rules(findings)


def test_v14_refused_ending_with_empty_says() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: DONE }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "" }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V14" in _rules(findings)


def test_v14_refused_end_naming_an_undeclared_ending() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: NOT_DECLARED }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V14" in _rules(findings)


def test_v14_accepted_end_naming_an_engine_ending() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
start: a
nodes:
  a: { type: STEP, tool: echo@1, in: { value: inputs.x }, out: {}, end: ESCALATED }
inputs: { x: { type: string } }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    findings = validate(doc, registry=_base_registry())
    assert "V14" not in _rules(findings)


# ------------------------------------------------------------------------------ V15 --


def test_v15_accepted_profile_enum_with_grounded_in() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROFILE
id: severity-level
version: 1.0.0
title: Severity level
grounded_in: RFC 5424 6.2.1 (two-value subset)
schema:
  type: object
  properties:
    severity: { type: string, enum: [ERROR, WARNING] }
"""
    findings = validate(doc, registry=Registry())
    assert "V15" not in _rules(findings)


def test_v15_refused_profile_enum_with_no_grounded_in() -> None:
    doc = """
api_version: sulis.workflows/v1
kind: PROFILE
id: severity-level
version: 1.0.0
title: Severity level
schema:
  type: object
  properties:
    severity: { type: string, enum: [ERROR, WARNING] }
"""
    findings = validate(doc, registry=Registry())
    assert "V15" in _rules(findings)


# ------------------------------------------------------------------------------ V16 --


def test_v16_accepted_upsert_by_id_channel_with_key() -> None:
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, "
        "out: { verdict: state.verdict }, end: DONE }",
        extra_state='  insights: { type: "list<any>", reducer: UPSERT_BY_ID, key: id }\n',
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V16" not in _rules(findings)


def test_v16_refused_upsert_by_id_channel_with_no_key() -> None:
    """The bad-but-conformant case: a channel that calls itself UPSERT_BY_ID
    but never names what to upsert by — schema-valid (§14/V1 leaves `key`
    optional), still refused."""
    doc = _process_with_step(
        "    { type: STEP, tool: interrogate@1, in: { question: inputs.question }, "
        "out: { verdict: state.verdict }, end: DONE }",
        extra_state='  insights: { type: "list<any>", reducer: UPSERT_BY_ID }\n',
    )
    findings = validate(doc, registry=_base_registry(_INTERROGATE_TOOL))
    assert "V16" in _rules(findings)


# ------------------------------------------------------------------------------ V17 --


def test_v17_accepted_code_mechanism() -> None:
    findings = validate(ECHO_TOOL, registry=_base_registry())
    assert "V17" not in _rules(findings)


def test_v17_refused_external_mechanism() -> None:
    """D34: spec §4.3/§12.1 — EXTERNAL is a real mechanism kind meant to
    run BY THE ENGINE (through a host adapter), but nothing in the engine
    implements dispatch for it; refused rather than silently misrouted as
    a SKILL hand-off."""
    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: notify-external
version: 1.0.0
title: Notify (external)
inputs: { value: { type: string } }
output: { value: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism: { kind: EXTERNAL, ref: "adapter:notify" }
effect: SIDE_EFFECT
"""
    findings = validate(doc, registry=_base_registry())
    assert "V17" in _rules(findings)


def test_v17_refused_tool_composite_mechanism() -> None:
    """D34: TOOL (composite) is a real mechanism kind — child Tools run in
    order over shared values (spec §4.3) — but nothing in the engine
    dispatches `composes`; refused rather than silently misrouted as an
    opaque SKILL hand-off with no instructions."""
    doc = """
api_version: sulis.workflows/v1
kind: TOOL
id: composite-echo
version: 1.0.0
title: Composite echo
inputs: { value: { type: string } }
output: { value: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism:
  kind: TOOL
  composes:
    - { tool: echo@1, inputs: { value: inputs.value }, output: { value: value } }
effect: QUERY
"""
    findings = validate(doc, registry=_base_registry())
    assert "V17" in _rules(findings)


# ------------------------------------------------------------------------------ D35 --
# An inline PROCESS body (spec §9.1, D18) is a Process-shaped sequence of its
# own (start/nodes/state/endings) — these confirm it is now checked by the
# same rules a top-level Process document is, not skipped entirely.

_INLINE_TOOL_TEMPLATE = """
api_version: sulis.workflows/v1
kind: TOOL
id: inline-tool
version: 1.0.0
title: Inline tool
inputs: { value: { type: string } }
output: { value: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism:
  kind: PROCESS
  process:
    start: step-a
    nodes:
      step-a: { type: STEP, tool: echo@1, in: { value: state.value }, out: { value: state.value }, end: __STEP_END__ }
    state:
      value: { type: string, reducer: REPLACE, default: "" }
    endings:
      DONE: { outcome: SUCCESS, says: "Done." }
  result: { outputs: { value: state.value }, endings: { DONE: DONE } }
effect: QUERY
"""


def test_inline_process_body_accepted_when_internally_well_formed() -> None:
    doc = _INLINE_TOOL_TEMPLATE.replace("__STEP_END__", "DONE")
    findings = validate(doc, registry=_base_registry())
    assert not [f for f in findings if "inline process body" in f.message]


def test_inline_process_body_refused_for_an_undeclared_ending() -> None:
    """D35: before this fix, nothing recursed into `mechanism.process` at
    all — a StepNode's own `end:` naming an ending the inline body never
    declares (V14's job for a top-level Process) passed validation with
    zero findings and only surfaced as an uncaught `EngineRefusal` the
    first time a run actually reached it."""
    doc = _INLINE_TOOL_TEMPLATE.replace("__STEP_END__", "NOT_DECLARED")
    findings = validate(doc, registry=_base_registry())
    assert "V14" in _rules(findings)
    assert any(
        "inline-tool" in f.message and "inline process body" in f.message
        for f in findings
    )


def test_inline_process_body_refused_for_an_unresolvable_tool_reference() -> None:
    """D35: the V2 half of the same gap — `_v2_mechanism_references`'s own
    docstring already flagged that an inline body's internal `tool:`
    references were never resolved before this fix. Checks for the
    specific 'no-such-tool' finding, not just any V2 finding — this
    fixture's own outer `controls: [{ profile: finding@1 }]` already
    produces an unrelated V2 finding (the 'finding' profile is not
    registered by `_base_registry()`) regardless of this fix."""
    doc = _INLINE_TOOL_TEMPLATE.replace("tool: echo@1", "tool: no-such-tool@1").replace(
        "__STEP_END__", "DONE"
    )
    findings = validate(doc, registry=_base_registry())
    assert any(f.rule == "V2" and "no-such-tool" in f.message for f in findings)


def test_spec_worked_examples_own_inline_process_fixture_is_internally_clean() -> None:
    """D35: `tests/definition/fixtures/accepted/tool-process-inline.yaml`
    mirrors §9.1's own worked example — before this fix, its inline
    body's `state.current`/`state.survived` were read/written without
    ever being declared in its own `state:` block, an undeclared-channel
    gap V5 already refuses for a top-level Process, just never checked
    here. Confirmed and fixed alongside this fix (both the fixture and
    the spec's own snippet now declare `state:`)."""
    doc = (_FIXTURES / "accepted" / "tool-process-inline.yaml").read_text()
    attack_claim_tool = """
api_version: sulis.workflows/v1
kind: TOOL
id: attack-claim
version: 1.0.0
title: Attack claim
inputs: { candidate: { type: "profile:finding@1" } }
output: { survived: { type: boolean } }
controls: [ { conventions: faithful-generation@1 } ]
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
effect: QUERY
"""
    registry = Registry([load_definition(attack_claim_tool, fmt="yaml")])
    findings = validate(doc, registry=registry)
    assert not [f for f in findings if "inline process body" in f.message]
