"""attempt_step — one STEP dispatch attempt (spec §7.1, §10, §12.4, WP-02 step 2).

Covers the CODE-mechanism path only (this PR's scope): permission, then
precondition, then input resolution, then dispatch, then controls — in
that order, each one able to stop the attempt before the next runs.
"""

from __future__ import annotations

import asyncio

from sulis_workflows.definition.model import (
    ControlRef,
    ErrorSpec,
    Header,
    InputSpec,
    Mechanism,
    OutputSpec,
    Profile,
    StepNode,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.code_tool import (
    StubCodeToolAdapter,
    ToolPermanentError,
    ToolTransientError,
)
from sulis_workflows.domain.ports.policy import StubPolicyAdapter
from sulis_workflows.engine.steps import (
    ENGINE_INPUT_UNRESOLVED,
    StepOutcome,
    attempt_step,
)


def _header(id_: str, kind: str) -> Header:
    return Header(
        api_version="sulis.workflows/v1", kind=kind, id=id_, version="1.0.0", title=id_
    )


def _insight_profile() -> Profile:
    return Profile(
        header=_header("insight", "PROFILE"),
        schema={
            "type": "object",
            "required": ["id", "claim"],
            "properties": {"id": {"type": "string"}, "claim": {"type": "string"}},
            "additionalProperties": False,
        },
    )


def _tool(**overrides) -> Tool:
    defaults = {
        "header": _header("conclude", "TOOL"),
        "output": {"insight": OutputSpec(type="profile:insight@1")},
        "controls": (ControlRef(kind="profile", ref="insight@1"),),
        "mechanism": Mechanism(kind="CODE", ref="mod:fn"),
        "effect": "QUERY",
        "inputs": {"question": InputSpec(type="string")},
        "permission": "workflows.conclude.dispatch",
    }
    defaults.update(overrides)
    return Tool(**defaults)


def _node(**overrides) -> StepNode:
    defaults = {
        "id": "conclude",
        "tool": "conclude@1",
        "in_": {"question": "state.question"},
        "out": {"insight": "state.insight"},
    }
    defaults.update(overrides)
    return StepNode(**defaults)


def _run(node, tool, run_state, *, policy=None, code_tool=None, registry=None):
    return asyncio.run(
        attempt_step(
            node,
            tool,
            run_state,
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
            policy=policy or StubPolicyAdapter(),
            code_tool=code_tool or StubCodeToolAdapter(),
            registry=registry or Registry([_insight_profile()]),
        )
    )


def test_tool_with_no_declared_permission_is_forbidden_not_skipped():
    result = _run(_node(), _tool(permission=None), {"state": {"question": "why"}})
    assert result.outcome is StepOutcome.FORBIDDEN


def test_permission_denied_is_forbidden():
    policy = StubPolicyAdapter(denies={"workflows.conclude.dispatch"})
    result = _run(_node(), _tool(), {"state": {"question": "why"}}, policy=policy)
    assert result.outcome is StepOutcome.FORBIDDEN


def test_permission_indeterminate_fails_closed_as_forbidden():
    policy = StubPolicyAdapter(indeterminate={"workflows.conclude.dispatch"})
    result = _run(_node(), _tool(), {"state": {"question": "why"}}, policy=policy)
    assert result.outcome is StepOutcome.FORBIDDEN


def test_false_precondition_stops_before_dispatch():
    node = _node(precondition="len(state.findings) > 0")
    code_tool = StubCodeToolAdapter()
    result = _run(
        node,
        _tool(),
        {"state": {"question": "why", "findings": []}},
        code_tool=code_tool,
    )
    assert result.outcome is StepOutcome.PRECONDITION_FALSE
    assert code_tool.observed_calls == []


def test_missing_required_input_is_reported_not_dispatched():
    code_tool = StubCodeToolAdapter()
    result = _run(_node(), _tool(), {"state": {}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.INPUT_UNRESOLVED
    assert result.error_code == ENGINE_INPUT_UNRESOLVED
    assert code_tool.observed_calls == []


def test_ordered_input_paths_use_first_present_non_empty_value():
    node = _node(in_={"question": ["state.framed_question", "inputs.brief_question"]})
    code_tool = StubCodeToolAdapter(
        responses={"mod:fn": {"insight": {"id": "i", "claim": "c"}}}
    )
    run_state = {"state": {"framed_question": ""}, "inputs": {"brief_question": "why"}}
    result = _run(node, _tool(), run_state, code_tool=code_tool)
    assert result.outcome is StepOutcome.SUCCESS
    assert code_tool.observed_calls == [("tenant-1", "run-1")]


def test_non_code_mechanism_is_not_dispatchable_yet():
    tool = _tool(mechanism=Mechanism(kind="AGENTIC", ref="skills/conclude"))
    code_tool = StubCodeToolAdapter()
    result = _run(_node(), tool, {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.NOT_DISPATCHABLE
    assert code_tool.observed_calls == []


def test_transient_error_is_classified_from_the_tools_own_errors_list():
    tool = _tool(
        errors=(ErrorSpec(code="SOURCE_UNREACHABLE", error_class="TRANSIENT"),)
    )
    code_tool = StubCodeToolAdapter(
        raises={"mod:fn": ToolTransientError("SOURCE_UNREACHABLE")}
    )
    result = _run(_node(), tool, {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.ERROR
    assert result.error_code == "SOURCE_UNREACHABLE"
    assert result.error_class == "TRANSIENT"


def test_an_undeclared_error_code_classifies_as_permanent():
    # spec S4.6: "An unlisted error is PERMANENT" — even if the adapter raised
    # ToolTransientError, the Tool's own declared errors[] is authoritative.
    tool = _tool(errors=())
    code_tool = StubCodeToolAdapter(
        raises={"mod:fn": ToolTransientError("SOMETHING_UNNAMED")}
    )
    result = _run(_node(), tool, {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.ERROR
    assert result.error_class == "PERMANENT"


def test_permanent_error_is_classified_permanent():
    tool = _tool(
        errors=(ErrorSpec(code="BRIEF_UNANSWERABLE", error_class="PERMANENT"),)
    )
    code_tool = StubCodeToolAdapter(
        raises={"mod:fn": ToolPermanentError("BRIEF_UNANSWERABLE")}
    )
    result = _run(_node(), tool, {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.ERROR
    assert result.error_class == "PERMANENT"


def test_successful_dispatch_with_passing_controls_is_success():
    code_tool = StubCodeToolAdapter(
        responses={"mod:fn": {"insight": {"id": "i1", "claim": "c"}}}
    )
    result = _run(_node(), _tool(), {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.SUCCESS
    assert result.output == {"insight": {"id": "i1", "claim": "c"}}
    assert result.controls is not None and result.controls.all_passed


def test_dispatch_with_failing_control_is_control_failed_not_success():
    code_tool = StubCodeToolAdapter(
        responses={"mod:fn": {"insight": {"id": "i1"}}}
    )  # missing claim
    result = _run(_node(), _tool(), {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.CONTROL_FAILED
    assert result.controls is not None and not result.controls.all_passed


def test_a_control_this_engine_cannot_check_refuses_rather_than_silently_passes():
    tool = _tool(
        controls=(ControlRef(kind="conventions", ref="faithful-generation@1"),)
    )
    code_tool = StubCodeToolAdapter(
        responses={"mod:fn": {"insight": {"id": "i1", "claim": "c"}}}
    )
    result = _run(_node(), tool, {"state": {"question": "why"}}, code_tool=code_tool)
    assert result.outcome is StepOutcome.CONTROLS_UNCHECKABLE
