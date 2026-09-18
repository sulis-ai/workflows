"""V5 — the spec §8 expression grammar: parser, type checker, evaluator."""

from __future__ import annotations

import pytest

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.expressions import (
    TypeContext,
    evaluate,
    infer_type,
    parse,
)
from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry


def _registry() -> Registry:
    tool = load_definition(
        """
api_version: sulis.workflows/v1
kind: TOOL
id: interrogate
version: 1.0.0
title: Interrogate
inputs: { question: { type: string } }
output:
  insights: { type: "list<profile:insight@1>" }
  verdict:  { type: "enum[SURVIVED, DROPPED, REVISED]" }
controls: [ { profile: insight@1 } ]
mechanism: { kind: AGENTIC, ref: skills/interrogate }
effect: QUERY
""",
        fmt="yaml",
    )
    return Registry([tool])


def _process():
    return load_definition(
        """
api_version: sulis.workflows/v1
kind: PROCESS
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: string }
host_inputs:
  topology_index: { type: any }
state:
  path:       { type: "enum[SINGLE, RECURSIVE]", reducer: REPLACE }
  confidence: { type: "enum[GROUNDED, PARTIAL, INSUFFICIENT]", reducer: REPLACE }
  findings:   { type: "list<profile:finding@1>", reducer: APPEND }
  score:      { type: number, reducer: REPLACE }
start: interrogate
nodes:
  interrogate:
    { type: STEP, tool: interrogate@1, in: { question: state.path }, out: {}, next: sign-off }
  sign-off:
    type: GATE
    asks: "Proceed?"
    on:
      PERMIT: { end: COMPLETE }
      DENY: { end: DENIED }
endings:
  COMPLETE: { outcome: SUCCESS, says: "Done." }
  DENIED: { outcome: STOPPED, says: "Refused." }
""",
        fmt="yaml",
    )


def _ctx() -> TypeContext:
    return TypeContext(_process(), _registry())


# -------------------------------------------------------------------------- parser --


@pytest.mark.parametrize(
    "text",
    [
        'state.path == "SINGLE"',
        'state.path == "SINGLE" and state.confidence != "INSUFFICIENT"',
        "not exists(state.score)",
        "len(state.findings) > 0",
        '"SINGLE" in ["SINGLE", "RECURSIVE"]',
        "(state.score >= 1) or (state.score <= 0)",
    ],
)
def test_well_formed_expressions_parse(text: str) -> None:
    parse(text)  # does not raise


@pytest.mark.parametrize(
    "text",
    [
        "",
        "state.path ==",
        'state.path == "SINGLE',  # unterminated string
        '(state.path == "SINGLE"',  # unbalanced paren
        "state..path",
        'state.path === "SINGLE"',
        "1 2",
    ],
)
def test_malformed_expressions_are_refused(text: str) -> None:
    with pytest.raises(DefinitionError) as excinfo:
        parse(text)
    assert excinfo.value.rule == "V5"


# --------------------------------------------------------------------- type checker --


def test_declared_paths_type_check() -> None:
    ctx = _ctx()
    assert infer_type(parse("state.path"), ctx).__class__.__name__ == "TEnum"
    assert infer_type(parse("inputs.brief"), ctx).__class__.__name__ == "TString"
    assert infer_type(parse("host.topology_index"), ctx).__class__.__name__ == "TAny"
    assert (
        infer_type(parse("steps.interrogate.output.verdict"), ctx).__class__.__name__
        == "TEnum"
    )
    assert (
        infer_type(parse("steps.sign-off.verdict"), ctx).__class__.__name__ == "TEnum"
    )


def test_can_drill_one_level_into_a_profile_typed_input() -> None:
    """spec Appendix A reads `inputs.brief.question` — one level into the
    `brief` profile's own schema."""

    brief_profile = load_definition(
        """
api_version: sulis.workflows/v1
kind: PROFILE
id: brief
version: 1.0.0
title: Brief
grounded_in: this format's own convention
schema:
  type: object
  required: [question]
  properties:
    question: { type: string }
    priority: { type: integer }
""",
        fmt="yaml",
    )
    process = load_definition(
        """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
inputs:
  brief: { type: "profile:brief@1" }
start: a
nodes:
  a: { type: STEP, tool: interrogate@1, in: { question: inputs.brief.question }, out: {}, end: DONE }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
""",
        fmt="yaml",
    )
    ctx = TypeContext(
        process, Registry([brief_profile, _registry().resolve("TOOL", "interrogate@1")])
    )
    assert (
        infer_type(parse("inputs.brief.question"), ctx).__class__.__name__ == "TString"
    )
    assert (
        infer_type(parse("inputs.brief.priority"), ctx).__class__.__name__ == "TInteger"
    )
    with pytest.raises(DefinitionError):
        infer_type(parse("inputs.brief.nonexistent"), ctx)


def test_undeclared_path_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("state.does_not_exist"), _ctx())
    assert excinfo.value.rule == "V5"


def test_undeclared_input_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("inputs.does_not_exist"), _ctx())
    assert excinfo.value.rule == "V5"


def test_unknown_node_in_steps_path_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("steps.nonexistent.output.verdict"), _ctx())
    assert excinfo.value.rule == "V5"


def test_unknown_tool_output_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("steps.interrogate.output.does_not_exist"), _ctx())
    assert excinfo.value.rule == "V5"


def test_step_level_verdict_on_a_step_node_has_no_declared_type() -> None:
    # steps.<node>.verdict is only typed for a GATE (spec §7.6's PERMIT/DENY/INDETERMINATE);
    # a STEP node's own generic per-attempt "verdict" field has no spec-given type.
    with pytest.raises(DefinitionError):
        infer_type(parse("steps.interrogate.verdict"), _ctx())


def test_enum_compared_with_a_value_outside_it_is_refused() -> None:
    """The spec §8/§14 (V5) named bad-but-conformant case, verbatim: an expression
    comparing an enum path with a value outside the enum."""

    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse('state.path == "SIDEWAYS"'), _ctx())
    assert excinfo.value.rule == "V5"
    assert "SIDEWAYS" in str(excinfo.value)


def test_enum_compared_with_a_declared_member_is_accepted() -> None:
    infer_type(parse('state.path == "SINGLE"'), _ctx())  # does not raise


def test_ordering_comparison_between_incompatible_types_is_refused() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("state.path > state.score"), _ctx())
    assert excinfo.value.rule == "V5"


def test_ordering_comparison_between_numbers_is_accepted() -> None:
    infer_type(parse("state.score > 0"), _ctx())


def test_in_requires_a_list_on_the_right() -> None:
    with pytest.raises(DefinitionError) as excinfo:
        infer_type(parse("state.score in state.confidence"), _ctx())
    assert excinfo.value.rule == "V5"


def test_in_with_a_list_literal_is_accepted() -> None:
    infer_type(parse('state.path in ["SINGLE", "RECURSIVE"]'), _ctx())


def test_exists_and_len_still_type_check_their_inner_path() -> None:
    with pytest.raises(DefinitionError):
        infer_type(parse("exists(state.does_not_exist)"), _ctx())
    with pytest.raises(DefinitionError):
        infer_type(parse("len(state.does_not_exist)"), _ctx())


# ------------------------------------------------------------------------- evaluator --


def test_evaluate_comparison() -> None:
    state = {"state": {"path": "SINGLE"}}
    assert evaluate(parse('state.path == "SINGLE"'), state) is True
    assert evaluate(parse('state.path == "RECURSIVE"'), state) is False


def test_evaluate_and_or_not() -> None:
    state = {"state": {"path": "SINGLE", "confidence": "GROUNDED"}}
    assert (
        evaluate(
            parse('state.path == "SINGLE" and state.confidence == "GROUNDED"'), state
        )
        is True
    )
    assert (
        evaluate(
            parse('state.path == "SINGLE" and state.confidence == "PARTIAL"'), state
        )
        is False
    )
    assert (
        evaluate(
            parse('state.path == "RECURSIVE" or state.confidence == "GROUNDED"'), state
        )
        is True
    )
    assert evaluate(parse('not (state.path == "RECURSIVE")'), state) is True


def test_evaluate_exists_and_len() -> None:
    state = {"state": {"findings": [1, 2, 3]}}
    assert evaluate(parse("exists(state.findings)"), state) is True
    assert evaluate(parse("exists(state.missing)"), state) is False
    assert evaluate(parse("len(state.findings)"), state) == 3
    assert evaluate(parse("len(state.missing)"), state) == 0


def test_comparing_an_absent_value_is_false_never_an_error() -> None:
    state: dict = {"state": {}}
    assert evaluate(parse("state.missing == 1"), state) is False
    assert evaluate(parse("state.missing != 1"), state) is False
    assert evaluate(parse("state.missing > 1"), state) is False


def test_evaluate_in_operator() -> None:
    state = {"state": {"path": "SINGLE"}}
    assert evaluate(parse('state.path in ["SINGLE", "RECURSIVE"]'), state) is True
    assert evaluate(parse('state.path in ["RECURSIVE"]'), state) is False


def test_evaluate_indexed_path() -> None:
    state = {"state": {"items": [{"id": "a"}, {"id": "b"}]}}
    assert evaluate(parse("state.items[1].id"), state) == "b"
